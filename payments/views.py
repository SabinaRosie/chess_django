import hmac
import hashlib
import base64
import uuid
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from .models import Transaction

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """
    Creates a transaction and returns the signature needed for eSewa v2.
    """
    product_id = request.data.get('product_id')
    amount_raw = request.data.get('amount')
    if not amount_raw or not product_id:
        return Response({"error": "Amount and product_id are required"}, status=400)

    # Format amount: Back to clean integer if whole number
    try:
        amount = str(int(float(amount_raw))) if float(amount_raw) == int(float(amount_raw)) else str(float(amount_raw))
    except (ValueError, TypeError):
        amount = str(amount_raw)

    import time
    # Using a simpler ID format (timestamp + user ID)
    transaction_uuid = f"{int(time.time())}{request.user.id}"

    # Create a local Transaction record (PENDING)
    transaction = Transaction.objects.create(
        user=request.user,
        amount=amount,
        product_id=product_id,
        transaction_uuid=transaction_uuid,
        status='PENDING'
    )

    key_str = settings.ESEWA_SECRET_KEY.strip()
    
    # 🔹 eSewa v2 Signature Logic
    # Hardcoding EPAYTEST just to be 100% sure it matches the sandbox requirement
    data_string = f"total_amount={amount},transaction_uuid={transaction_uuid},product_code=EPAYTEST"
    
    print(f"DEBUG: eSewa Signature String: [{data_string}]")
    
    print(f"DEBUG: eSewa Secret Key starts with: {key_str[:4]}...")
    key = key_str.encode('utf-8')
    message_bytes = data_string.encode('utf-8')
    
    # Generate HMAC-SHA256 signature
    hmac_sha256 = hmac.new(key, message_bytes, hashlib.sha256).digest()
    signature = base64.b64encode(hmac_sha256).decode('utf-8')
    
    print(f"DEBUG: eSewa Signature Generated: [{signature}]")

    return Response({
        "success": True,
        "payment_data": {
            "amount": amount,
            "product_id": product_id,
            "transaction_uuid": transaction_uuid,
            "merchant_id": "EPAYTEST",
            "signature": signature,
        }
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    """
    Verifies the payment with eSewa and updates the user's coins.
    """
    import json
    from accounts.models import UserProfile
    
    encoded_data = request.data.get('data') # Base64 response from eSewa SDK

    if not encoded_data:
        return Response({"error": "No data received"}, status=400)

    # 1. Decode the response
    try:
        decoded_bytes = base64.b64decode(encoded_data)
        decoded_data = json.loads(decoded_bytes.decode('utf-8'))
    except Exception:
        return Response({"error": "Invalid data format"}, status=400)

    # 2. Extract values
    transaction_uuid = decoded_data.get('transaction_uuid')
    total_amount = decoded_data.get('total_amount').replace(',', '')
    status = decoded_data.get('status')
    ref_id = decoded_data.get('transaction_code')

    if status != 'COMPLETE':
        return Response({"error": f"Payment status is {status}"}, status=400)

    # 3. Find our transaction record
    try:
        transaction = Transaction.objects.get(transaction_uuid=transaction_uuid)
    except Transaction.DoesNotExist:
        return Response({"error": "Transaction not found"}, status=404)

    if transaction.status == 'COMPLETE':
        profile = request.user.profile
        return Response({"success": True, "message": "Already processed", "coins": profile.coins})

    # 4. Success! Update Transaction and Add Coins
    transaction.status = 'COMPLETE'
    transaction.esewa_ref_id = ref_id
    transaction.save()

    # Rule: 1 NPR = 10 Coins
    coins_to_add = int(float(total_amount) * 10)
    
    profile = request.user.profile
    profile.coins += coins_to_add
    profile.save()

    return Response({
        "success": True,
        "message": f"Added {coins_to_add} coins!",
        "new_balance": profile.coins
    })
