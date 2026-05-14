import hmac
import hashlib
import base64

secret_key = "8g8M8m8P8p8P8m8M"
message = "total_amount=100,transaction_uuid=177876739011,product_code=EPAYTEST"

key = secret_key.encode('utf-8')
message_bytes = message.encode('utf-8')
hmac_sha256 = hmac.new(key, message_bytes, hashlib.sha256).digest()
signature = base64.b64encode(hmac_sha256).decode('utf-8')

print(f"Calculated: {signature}")
print(f"Matches: {signature == 'd/CO1xh0lJlERm0v51LkzyDtQiDS7pD1c1eu1U2jRVo='}")
