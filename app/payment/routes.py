import os
from flask import render_template, request, jsonify, redirect, url_for, current_app
from flask_login import login_required, current_user
from . import payment_bp
import requests
import json
from app import Config
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import firestore, credentials
import logging
import traceback
from payos import PayOS, ItemData, PaymentData
from app.models.user import User

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize PayOS client
payos = PayOS(
    client_id=os.getenv('PAYOS_CLIENT_ID'),
    api_key=os.getenv('PAYOS_API_KEY'),
    checksum_key=os.getenv('PAYOS_CHECKSUM_KEY')
)

def get_firestore_db():
    try:
        return firestore.client()
    except ValueError as e:
        logger.error(f"Firebase initialization error: {str(e)}")
        try:
            cred = credentials.Certificate(current_app.config['FIREBASE_ADMIN_SDK_PATH'])
            firebase_admin.initialize_app(cred)
            return firestore.client()
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}")
            raise

def update_user_role(user_id, role='member'):
    """Update user role in Firestore"""
    try:
        db = get_firestore_db()
        user_ref = db.collection('users').document(user_id)
        user_ref.update({
            'role': role,
            'role_updated_at': datetime.now()
        })
        logger.debug(f"Updated user {user_id} role to {role}")
    except Exception as e:
        logger.error(f"Error updating user role: {str(e)}")
        raise

def update_user_subscription(user_id, plan_type, order_code):
    """Update user subscription in Firestore"""
    try:
        db = get_firestore_db()
        user_ref = db.collection('users').document(user_id)
        
        # Calculate subscription end date
        now = datetime.now()
        if plan_type == 'monthly':
            end_date = now + timedelta(days=30)
        else:  # yearly
            end_date = now + timedelta(days=365)
        
        # Update user subscription
        user_ref.update({
            'subscription_type': plan_type,
            'subscription_status': 'active',
            'subscription_start_date': now,
            'subscription_end_date': end_date,
            'last_payment_order_code': order_code
        })
        
        # Update user role to member
        update_user_role(user_id)
        
        logger.debug(f"Updated subscription for user {user_id}")
    except Exception as e:
        logger.error(f"Error updating user subscription: {str(e)}")
        raise

def payment_result_to_dict(payment_result):
    """Convert PayOS payment result to dictionary for Firestore storage"""
    return {
        'bin': payment_result.bin,
        'accountNumber': payment_result.accountNumber,
        'accountName': payment_result.accountName,
        'amount': payment_result.amount,
        'description': payment_result.description,
        'orderCode': payment_result.orderCode,
        'currency': payment_result.currency,
        'paymentLinkId': payment_result.paymentLinkId,
        'status': payment_result.status,
        'checkoutUrl': payment_result.checkoutUrl,
        'expiredAt': payment_result.expiredAt
    }

@payment_bp.route('/subscribe')
@login_required
def subscribe():
    return render_template('subscribe.html')

@payment_bp.route('/create', methods=['POST'])
@login_required
def create_payment():
    try:
        # Log the incoming request
        logger.debug(f"Received payment request from user {current_user.id}")
        
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({
                'success': False,
                'error': 'Request must be JSON'
            }), 400

        data = request.get_json()
        logger.debug(f"Request data: {data}")
        
        # Validate required fields
        required_fields = ['amount', 'plan_type']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            logger.error(f"Missing required fields: {missing_fields}")
            return jsonify({
                'success': False,
                'error': f"Missing required fields: {', '.join(missing_fields)}"
            }), 400

        amount = data.get('amount')
        description = data.get('description', 'Payment for Shware service')
        plan_type = data.get('plan_type')
        
        if not plan_type or plan_type not in ['monthly', 'yearly']:
            logger.error(f"Invalid plan type: {plan_type}")
            return jsonify({
                'success': False,
                'error': 'Invalid plan type'
            }), 400
        
        # Create payment request using PayOS SDK
        order_code = int(datetime.now().timestamp())
        items = [ItemData(name=description, quantity=1, price=amount)]
        
        payment_data = PaymentData(
            orderCode=order_code,
            amount=amount,
            description=description,
            items=items,
            cancelUrl=url_for('payment.payment_cancel', _external=True),
            returnUrl=url_for('payment.payment_success', _external=True)
        )

        logger.debug(f"PayOS payment data: {payment_data}")

        try:
            # Create payment link using PayOS SDK
            payment_result = payos.createPaymentLink(payment_data)
            logger.debug(f"PayOS payment result: {payment_result}")
            
            # Store only essential payment information in Firestore
            db = get_firestore_db()
            payment_record = {
                'user_id': current_user.id,
                'amount': amount,
                'plan_type': plan_type,
                'order_code': order_code,
                'status': 'pending',
                'created_at': datetime.now(),
                'checkout_url': payment_result.checkoutUrl
            }
            
            logger.debug(f"Storing payment record: {payment_record}")
            db.collection('payments').add(payment_record)
            
            return jsonify({
                'success': True,
                'checkout_url': payment_result.checkoutUrl
            })
            
        except Exception as e:
            logger.error(f"PayOS SDK error: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    except Exception as e:
        logger.error(f"Payment creation error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@payment_bp.route('/success')
def payment_success():
    order_code = request.args.get('orderCode')
    if order_code:
        try:
            # Get payment information from PayOS
            payment_info = payos.getPaymentLinkInformation(order_code)
            
            # Update payment status in Firestore
            db = get_firestore_db()
            payments_ref = db.collection('payments')
            query = payments_ref.where('order_code', '==', int(order_code)).limit(1)
            docs = query.get()
            
            for doc in docs:
                payment_data = doc.to_dict()
                doc.reference.update({
                    'status': 'completed',
                    'completed_at': datetime.now()
                })
                
                # Update user subscription and role
                update_user_subscription(
                    payment_data['user_id'],
                    payment_data['plan_type'],
                    order_code
                )
        except Exception as e:
            logger.error(f"Error processing successful payment: {str(e)}")
            logger.error(traceback.format_exc())
    
    return render_template('payment_success.html')

@payment_bp.route('/cancel')
def payment_cancel():
    order_code = request.args.get('orderCode')
    if order_code:
        try:
            # Update payment status in Firestore
            db = get_firestore_db()
            payments_ref = db.collection('payments')
            query = payments_ref.where('order_code', '==', int(order_code)).limit(1)
            docs = query.get()
            
            for doc in docs:
                doc.reference.update({
                    'status': 'cancelled',
                    'cancelled_at': datetime.now()
                })
        except Exception as e:
            logger.error(f"Error processing cancelled payment: {str(e)}")
            logger.error(traceback.format_exc())
    
    return render_template('payment_cancel.html')

@payment_bp.route('/webhook', methods=['POST'])
def payment_webhook():
    try:
        data = request.get_json()
        order_code = data.get('orderCode')
        
        # Verify webhook signature using PayOS SDK
        if not payos.verifyWebhookSignature(data):
            logger.error("Invalid webhook signature")
            return jsonify({'success': False, 'error': 'Invalid signature'}), 400
        
        # Update payment status in Firestore
        db = get_firestore_db()
        payments_ref = db.collection('payments')
        query = payments_ref.where('order_code', '==', int(order_code)).limit(1)
        docs = query.get()
        
        for doc in docs:
            payment_data = doc.to_dict()
            doc.reference.update({
                'status': data.get('status'),
                'webhook_data': data
            })
            
            if data.get('status') == 'completed':
                # Update user subscription and role
                update_user_subscription(
                    payment_data['user_id'],
                    payment_data['plan_type'],
                    order_code
                )
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500 