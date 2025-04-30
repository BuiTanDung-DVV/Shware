class PaymentError(Exception):
    """Base exception for payment-related errors"""
    pass

class PayOSError(PaymentError):
    """Exception for PayOS API-related errors"""
    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response

class InvalidSignatureError(PaymentError):
    """Exception for when payment signature validation fails"""
    pass

class PaymentValidationError(PaymentError):
    """Exception for payment validation errors"""
    pass

class PaymentAlreadyProcessedError(PaymentError):
    """Exception for when a payment is attempted to be processed more than once"""
    pass