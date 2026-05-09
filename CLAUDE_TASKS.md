Bohubrihi Organics — Claude Code Task List
> Hand this file to Claude Code. Work through tasks top to bottom. Each task is self-contained.
> Project location: `C:\Projects\bohubrihi`
> Live site: `https://bohubrihiorganics.com`
> Admin panel: `/admin` (password: admin123 — change this first)
---
HOW TO USE THIS FILE
Tell Claude Code:
> "Open CLAUDE_TASKS.md and complete Task 1" (or whichever task you want)
After each task, tell Claude Code:
> "Push to GitHub"
Render will auto-deploy within 2–3 minutes.
---
🔴 PHASE 0 — Critical Fixes (Do These First)
Task 0.1 — Fix 404 errors on product pages
Problem: `/product/skincare-starter-kit` and similar URLs return 404.
Fix: In `app.py`, the `product_detail` route uses integer ID (`/product/<int:pid>`). The URLs need to match. Check all product links in templates use `url_for('product_detail', pid=product.id)` not slug-based URLs.
File: `templates/store/shop.html`, `templates/store/index.html`
Check every product card link uses `{{ url_for('product_detail', pid=product.id) }}`
Task 0.2 — Add About page
Problem: `/about` returns 404.
Fix:
Add route in `app.py`:
```python
@app.route('/about')
def about():
    return render_template('store/about.html')
```
Create `templates/store/about.html` with brand story, values (100% Organic, No Chemicals, Made in Bangladesh), and team info.
Add About link to the navigation menu in `templates/base.html`.
Task 0.3 — Change admin password
Problem: Default password `admin123` is insecure.
Fix: In `app.py` line 15, replace the hash:
```python
import hashlib
# Generate new hash: hashlib.sha256(b'YOUR_NEW_PASSWORD').hexdigest()
ADMIN_PASSWORD_HASH = 'REPLACE_WITH_NEW_HASH'
```
Run this in Python to get the hash for your new password:
```python
import hashlib
print(hashlib.sha256(b'your_new_password').hexdigest())
```
---
🟡 PHASE 1 — Trust & Conversion
Task 1.1 — Show delivery charges at checkout
Problem: Delivery charges only shown after order is placed — causes cart abandonment.
Fix: In `templates/store/checkout.html`, add a visible delivery info section:
Dhaka: ৳60
Outside Dhaka: ৳120
Free delivery above ৳1500
Display this before the order summary. Update `app.py` checkout route to add delivery charge to the total based on the city field.
Task 1.2 — Add WhatsApp button (site-wide)
Fix: Add a floating WhatsApp button to `templates/base.html`:
```html
<a href="https://wa.me/8801XXXXXXXXX" target="_blank" 
   style="position:fixed; bottom:20px; right:20px; z-index:999;">
  <img src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" 
       width="55" height="55" alt="WhatsApp">
</a>
```
Replace `8801XXXXXXXXX` with the actual Bohubrihi WhatsApp number.
Task 1.3 — Add product ratings display
Fix: Add a `Rating` model to `app.py`:
```python
class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    customer_name = db.Column(db.String(100))
    rating = db.Column(db.Integer)  # 1-5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```
Add review submission form to `templates/store/product.html`
Display star ratings and reviews below product description
Add review management to admin panel
Task 1.4 — Add product bundles / "You May Also Like"
Fix: Already partially done (related products exist). Enhance `templates/store/product.html`:
Show related products section more prominently
Add "Complete the set" suggestion for complementary products
Add bundle discount logic (e.g., buy 3 soaps, get 10% off)
Task 1.5 — Fix admin sidebar UI
Problem: Admin sidebar is cramped and cut off on smaller screens.
Fix: Redesign `templates/admin/base.html` sidebar:
Use a collapsible sidebar
Fix overflow issues
Ensure all menu items are visible
Make it responsive for mobile
---
🟠 PHASE 2 — Analytics & Tracking
Task 2.1 — Add Google Analytics 4
Fix: In `templates/base.html`, add inside `<head>`:
```html
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```
Replace `G-XXXXXXXXXX` with actual GA4 Measurement ID from Google Analytics.
Steps to get ID: analytics.google.com → Admin → Create Property → Get Measurement ID
Task 2.2 — Add Facebook Pixel
Fix: In `templates/base.html`, add inside `<head>`:
```html
<!-- Facebook Pixel -->
<script>
!function(f,b,e,v,n,t,s){...}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init', 'YOUR_PIXEL_ID');
fbq('track', 'PageView');
</script>
```
Replace `YOUR_PIXEL_ID` with actual Pixel ID from Facebook Business Manager.
Also add `fbq('track', 'Purchase')` event in the order success page.
---
🔵 PHASE 3 — Payment Integration
Task 3.1 — bKash Payment Integration
Requirements:
bKash merchant credentials: `username`, `password`, `app_key`, `app_secret`
SSL certificate must be active on domain (required by bKash)
Add to `requirements.txt`:
```
pybkash
```
Add to `app.py`:
```python
from pybkash import Client, Token

BKASH_USERNAME = os.environ.get('BKASH_USERNAME')
BKASH_PASSWORD = os.environ.get('BKASH_PASSWORD')
BKASH_APP_KEY = os.environ.get('BKASH_APP_KEY')
BKASH_APP_SECRET = os.environ.get('BKASH_APP_SECRET')

@app.route('/bkash/create', methods=['POST'])
def bkash_create():
    token = Token(
        username=BKASH_USERNAME,
        password=BKASH_PASSWORD,
        app_key=BKASH_APP_KEY,
        app_secret=BKASH_APP_SECRET,
        sandbox=False  # Set True for testing
    )
    client = Client(token)
    amount = request.form.get('amount')
    payment = client.create_payment(
        callback_url=url_for('bkash_callback', _external=True),
        amount=amount
    )
    return redirect(payment.bkash_url)

@app.route('/bkash/callback')
def bkash_callback():
    payment_id = request.args.get('paymentID')
    status = request.args.get('status')
    if status == 'success':
        # Execute payment and save order
        pass
    return redirect(url_for('index'))
```
Add environment variables in Render Dashboard → Environment:
`BKASH_USERNAME`
`BKASH_PASSWORD`
`BKASH_APP_KEY`
`BKASH_APP_SECRET`
---
🟢 PHASE 4 — Database (Important for Production)
Task 4.1 — Migrate from SQLite to PostgreSQL
Problem: SQLite resets every time Render restarts (free tier spins down). All orders and products added via admin panel are lost.
Steps:
Create a free PostgreSQL database on Render:
Render Dashboard → New → PostgreSQL → Free tier
Copy the `Internal Database URL`
Add to `requirements.txt`:
```
psycopg2-binary
```
In `app.py`, change:
```python
# FROM:
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/bohubrihi.db'

# TO:
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:////tmp/bohubrihi.db')
```
Add environment variable in Render → Environment:
Key: `DATABASE_URL`
Value: (paste the Internal Database URL from step 1)
---
🚀 PHASE 5 — Growth Features
Task 5.1 — User accounts & order history
Add `User` model with email/password
Add login/register pages
Show order history in user dashboard
Link orders to user accounts
Task 5.2 — Skin type quiz
Create interactive quiz page at `/quiz`
5-6 questions about skin type, concerns, preferences
Recommend specific products based on answers
"Add recommended products to cart" button
Task 5.3 — Back-in-stock notifications
Add email field to out-of-stock product pages
Store emails in `Notification` model
When admin marks product as in-stock, send email to subscribers
Task 5.4 — Wishlist
Add `Wishlist` model
Heart icon on product cards
Saved to localStorage (no login required) or user account
Task 5.5 — Pathao Courier integration
API docs: https://pathao.com (developer section)
Auto-create shipment when order is confirmed
Show tracking number in order confirmation email
Update order status automatically via webhook
---
📋 QUICK REFERENCE
File    Purpose
`app.py`    All routes, models, business logic
`templates/base.html`    Site-wide header, footer, nav
`templates/store/index.html`    Homepage
`templates/store/shop.html`    Product listing
`templates/store/product.html`    Single product page
`templates/store/cart.html`    Cart
`templates/store/checkout.html`    Checkout form
`templates/admin/base.html`    Admin sidebar/layout
`templates/admin/dashboard.html`    Admin home
`static/css/style.css`    All custom styles
`static/js/store.js`    Cart logic, frontend JS
Push to GitHub command (run after every task)
```bash
git add -A
git commit -m "Task X.X — description"
git push origin master:main
```
