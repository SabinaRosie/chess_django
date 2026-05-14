import hmac
import hashlib
import base64

secret_key = "8g8M8m8P8p8P8m8M"
message = "total_amount=100,transaction_uuid=578ad5b1-34ee-4b66-a2d4-4bfa9e35deb4,product_code=EPAYTEST"

key = secret_key.encode('utf-8')
message_bytes = message.encode('utf-8')
hmac_sha256 = hmac.new(key, message_bytes, hashlib.sha256).digest()
signature = base64.b64encode(hmac_sha256).decode('utf-8')

print(f"Calculated: {signature}")
print(f"Matches: {signature == '4kGLu8c9+Z2O1IszrJW0/LuEI4uW1z1A44/66gAHCmk='}")
