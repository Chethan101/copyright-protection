import requests, time, io, random
from PIL import Image, ImageDraw

# Create unique image
r_val, g_val, b_val = random.randint(50,200), random.randint(50,200), random.randint(50,200)
img = Image.new('RGB', (200, 200), color=(r_val, g_val, b_val))
draw = ImageDraw.Draw(img)
draw.text((10,10), str(time.time()), fill=(255,255,255))
buf = io.BytesIO()
img.save(buf, format='JPEG')
img_bytes = buf.getvalue()

# Register on registry
u = f'u{int(time.time())}'
requests.post('http://127.0.0.1:8000/api/register', data={'username':u,'password':'pass'})
tok = requests.post('http://127.0.0.1:8000/api/login', data={'username':u,'password':'pass'}).json()['access_token']
reg = requests.post(
    'http://127.0.0.1:8000/api/images/register',
    headers={'Authorization': f'Bearer {tok}'},
    files={'file': ('img.jpg', img_bytes, 'image/jpeg')}
).json()
print('Registered! image_id:', reg.get('image_id'), '| tx_hash:', str(reg.get('tx_hash',''))[:20]+'...')
print('Watermark ID:', reg.get('watermark_id'))

# Download watermarked image
image_id = reg['image_id']
dl = requests.get(f'http://127.0.0.1:8000/api/images/{image_id}/download?token={tok}')
print('Download status:', dl.status_code, '| size:', len(dl.content), 'bytes')
wm_bytes = dl.content

# Try uploading to social as a DIFFERENT user (should be BLOCKED)
u2 = f'v{int(time.time())}'
requests.post('http://127.0.0.1:8001/api/register', data={'username':u2,'password':'pass'})
tok2 = requests.post('http://127.0.0.1:8001/api/login', data={'username':u2,'password':'pass'}).json()['access_token']
r2 = requests.post(
    'http://127.0.0.1:8001/api/posts/upload',
    headers={'Authorization': f'Bearer {tok2}'},
    files={'file': ('stolen.jpg', wm_bytes, 'image/jpeg')}
)
print('Social upload by thief - status:', r2.status_code, '(expected 403 = BLOCKED)')
if r2.status_code == 403:
    detail = r2.json()['detail']
    print('BLOCKED! Owner:', detail.get('owner_name'), '| Confidence:', detail.get('confidence'), '%')
    print('\n=== ALL TESTS PASSED ===')
else:
    print('NOT BLOCKED - Response:', r2.text[:300])
