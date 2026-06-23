from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
import os, json, hashlib, sys

try:
    from slack_sdk import WebClient as SlackClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    SlackClient = None
    SlackApiError = Exception

app = Flask(__name__)
app.config['SECRET_KEY'] = 'bohubrihi-secret-2024'
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///bohubrihi.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if _db_url.startswith('postgresql://'):
    # The Supabase session pooler recycles idle connections; pre_ping
    # detects a dropped connection and reconnects instead of raising.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
print(f"Database: {'PostgreSQL' if _db_url.startswith('postgresql://') else 'SQLite'}", file=sys.stderr)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ADMIN_PASSWORD_HASH = hashlib.sha256(b'admin123').hexdigest()

db = SQLAlchemy(app)


@app.context_processor
def inject_version():
    import time
    return dict(cache_bust=str(int(time.time())))


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True)
    icon = db.Column(db.String(10), default='🌿')
    sort_order = db.Column(db.Integer, default=0)
    products = db.relationship('Product', backref='category', lazy=True)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False)
    original_price = db.Column(db.Float, nullable=True)
    image = db.Column(db.String(300), default='')
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    in_stock = db.Column(db.Boolean, default=True)
    featured = db.Column(db.Boolean, default=False)
    ingredients = db.Column(db.Text, default='')
    weight = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviews = db.relationship('Review', backref='product', lazy=True)


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, default='')
    approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Bundle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False)
    original_price = db.Column(db.Float, nullable=False, default=0)
    image = db.Column(db.String(300), default='')
    in_stock = db.Column(db.Boolean, default=True)
    featured = db.Column(db.Boolean, default=False)
    is_deal = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('BundleItem', backref='bundle', lazy=True, cascade='all, delete-orphan')

    @property
    def savings(self):
        return max(self.original_price - self.price, 0)


class BundleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bundle_id = db.Column(db.Integer, db.ForeignKey('bundle.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    product = db.relationship('Product')


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_email = db.Column(db.String(200), nullable=False)
    customer_phone = db.Column(db.String(50), nullable=False)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(100), nullable=False)
    items_json = db.Column(db.Text, nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def items(self):
        return json.loads(self.items_json)


SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN', '')
SLACK_CHANNEL   = 'C0B2PQWLSR4'


def notify_slack_order(order, items):
    if not SlackClient:
        print("Slack: slack_sdk not installed", file=sys.stderr)
        return
    if not SLACK_BOT_TOKEN:
        print("Slack: SLACK_BOT_TOKEN env var not set", file=sys.stderr)
        return
    try:
        total_qty = sum(i['qty'] for i in items)
        lines = []
        for idx, item in enumerate(items, 1):
            weight = ""
            if item.get('type') != 'bundle':
                p = Product.query.get(item['id'])
                weight = f" {p.weight}" if p and p.weight else ""
            else:
                weight = " (Bundle)"
            lines.append(f"{idx}.{item['name']}{weight} - {item['qty']} pcs")
        text = (
            f"#{order.id}\n\n"
            f"Paid amount: {order.total:.0f}tk\n\n"
            f"Name: {order.customer_name}\n\n"
            f"Number: {order.customer_phone}\n\n"
            f"Address:\n"
            f"Area: {order.address}\n"
            f"District: {order.city}\n\n"
            f"Product list:\n"
            + "\n".join(lines) +
            f"\n\nTotal Products: {total_qty} pcs"
        )
        SlackClient(token=SLACK_BOT_TOKEN).chat_postMessage(channel=SLACK_CHANNEL, text=text)
        print(f"Slack: order #{order.id} notification sent", file=sys.stderr)
    except Exception as e:
        print(f"Slack error for order #{order.id}: {e}", file=sys.stderr)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '').strip()
SUPABASE_BUCKET = 'product-images'


def _log(msg):
    print(f"[SupabaseStorage] {msg}", file=sys.stderr, flush=True)


supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    _log(f"SUPABASE_URL set ({SUPABASE_URL[:30]}...), SUPABASE_KEY set (len={len(SUPABASE_KEY)})")
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        _log(f"Client created OK. Target bucket: '{SUPABASE_BUCKET}'")
        try:
            buckets = supabase_client.storage.list_buckets()
            bucket_names = [b.name for b in buckets]
            _log(f"Buckets visible to this key: {bucket_names}")
            if SUPABASE_BUCKET not in bucket_names:
                _log(f"WARNING: bucket '{SUPABASE_BUCKET}' not found in the list above. "
                     f"Check it exists in Supabase and the name matches exactly (case-sensitive).")
        except Exception as e:
            _log(f"WARNING: could not list buckets to verify '{SUPABASE_BUCKET}' exists "
                 f"({type(e).__name__}: {e}). Uploads will still be attempted.")
    except Exception as e:
        import traceback
        _log(f"ERROR: failed to create client, falling back to local uploads. "
             f"{type(e).__name__}: {e}")
        traceback.print_exc(file=sys.stderr)
        supabase_client = None
else:
    missing = []
    if not SUPABASE_URL:
        missing.append('SUPABASE_URL')
    if not SUPABASE_KEY:
        missing.append('SUPABASE_KEY')
    _log(f"Not configured (missing env var(s): {', '.join(missing)}). Using local static/uploads/.")


def _unique_filename(original_filename):
    filename = secure_filename(original_filename)
    base, ext = os.path.splitext(filename)
    return f"{base}_{int(datetime.utcnow().timestamp())}{ext}"


def save_uploaded_image(file_storage):
    """Save an uploaded image and return the value to store in the image column:
    a public URL when Supabase Storage is configured, otherwise a local filename."""
    if not file_storage or not file_storage.filename or not allowed_file(file_storage.filename):
        return ''
    filename = _unique_filename(file_storage.filename)

    if supabase_client:
        try:
            file_bytes = file_storage.read()
            content_type = file_storage.mimetype or 'application/octet-stream'
            _log(f"Uploading '{filename}' ({len(file_bytes)} bytes, {content_type}) "
                 f"to bucket '{SUPABASE_BUCKET}'...")
            supabase_client.storage.from_(SUPABASE_BUCKET).upload(
                filename, file_bytes, {'content-type': content_type}
            )
            url = supabase_client.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
            _log(f"Upload OK: {url}")
            return url
        except Exception as e:
            import traceback
            _log(f"ERROR: upload failed for '{filename}' in bucket '{SUPABASE_BUCKET}', "
                 f"falling back to local disk. {type(e).__name__}: {e}")
            traceback.print_exc(file=sys.stderr)
            # Fall through to local save so the admin doesn't lose the image entirely.
    else:
        _log(f"No client configured, saving '{filename}' locally instead.")

    file_storage.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename


def delete_uploaded_image(image_value):
    """Delete a previously saved image, whether it's a Supabase public URL or a local filename."""
    if not image_value:
        return
    if image_value.startswith('http://') or image_value.startswith('https://'):
        if not supabase_client:
            _log(f"Can't delete remote image '{image_value}': no client configured.")
            return
        try:
            marker = f'/object/public/{SUPABASE_BUCKET}/'
            if marker in image_value:
                path = image_value.split(marker, 1)[1]
                supabase_client.storage.from_(SUPABASE_BUCKET).remove([path])
                _log(f"Deleted '{path}' from bucket '{SUPABASE_BUCKET}'.")
            else:
                _log(f"WARNING: '{image_value}' doesn't match expected bucket path, skipping delete.")
        except Exception as e:
            import traceback
            _log(f"ERROR: delete failed for '{image_value}'. {type(e).__name__}: {e}")
            traceback.print_exc(file=sys.stderr)
    else:
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], image_value)
        if os.path.exists(local_path):
            os.remove(local_path)


@app.template_global()
def image_url(image):
    if not image:
        return ''
    if image.startswith('http://') or image.startswith('https://'):
        return image
    return url_for('static', filename='uploads/' + image)


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def seed_data():
    if Category.query.count() == 0:
        categories = [
            Category(name='Soaps', slug='soaps', icon='🧼', sort_order=1),
            Category(name='Face Care', slug='face-care', icon='✨', sort_order=2),
            Category(name='Creams & Lotions', slug='creams', icon='🧴', sort_order=3),
            Category(name='Hair Care', slug='hair-care', icon='💆', sort_order=4),
            Category(name='Body Care', slug='body-care', icon='🛁', sort_order=5),
            Category(name='Essential Oils', slug='essential-oils', icon='🌸', sort_order=6),
            Category(name='Gift Sets', slug='gift-sets', icon='🎁', sort_order=7),
        ]
        db.session.add_all(categories)
        db.session.commit()

        sample_products = [
            Product(name='Neem & Turmeric Soap', description='Antibacterial handcrafted soap with neem leaf extract and turmeric. Ideal for acne-prone skin.', price=180, original_price=220, category_id=1, featured=True, weight='100g'),
            Product(name='Rose Petal Soap', description='Luxurious soap infused with real rose petals and rose water for soft, fragrant skin.', price=200, category_id=1, weight='100g'),
            Product(name='Charcoal Detox Soap', description='Deep cleansing activated charcoal soap to draw out impurities from pores.', price=220, original_price=260, category_id=1, weight='100g'),
            Product(name='Aloe Vera Face Gel', description='Lightweight, soothing gel for all skin types. Hydrates and calms irritated skin.', price=350, category_id=2, featured=True, weight='100ml'),
            Product(name='Turmeric Face Mask', description='Brightening face mask with organic turmeric, multani mati, and sandalwood powder.', price=280, category_id=2, weight='50g'),
            Product(name='Rose Water Toner', description='Pure, alcohol-free rose water toner to refresh and balance skin pH.', price=250, original_price=300, category_id=2, weight='150ml'),
            Product(name='Shea Butter Body Lotion', description='Rich, nourishing lotion with shea butter and coconut oil for deeply moisturized skin.', price=400, category_id=3, featured=True, weight='200ml'),
            Product(name='Almond & Honey Cream', description='Intensive moisturizing cream with sweet almond oil and natural honey extracts.', price=380, category_id=3, weight='100g'),
            Product(name='Onion Hair Oil', description='Clinically proven onion extract hair oil for hair fall control and growth.', price=320, original_price=380, category_id=4, featured=True, weight='100ml'),
            Product(name='Amla & Bhringraj Hair Mask', description='Protein-rich hair mask to restore shine and strengthen hair from roots.', price=350, category_id=4, weight='200g'),
            Product(name='Coconut Milk Shampoo', description='Sulfate-free shampoo with coconut milk and argan oil for silky, frizz-free hair.', price=420, category_id=4, weight='200ml'),
            Product(name='Coffee Body Scrub', description='Exfoliating body scrub with fine coffee grounds and coconut oil for smooth skin.', price=360, category_id=5, weight='200g'),
            Product(name='Lavender Bath Salts', description='Relaxing Himalayan pink salt bath soak infused with lavender essential oil.', price=280, category_id=5, weight='300g'),
            Product(name='Tea Tree Essential Oil', description='100% pure therapeutic grade tea tree oil. Antiseptic and skin-clearing properties.', price=450, category_id=6, weight='15ml'),
            Product(name='Skincare Starter Kit', description='Perfect gift set with soap, toner, face mask, and moisturizer. Great for beginners.', price=950, original_price=1200, category_id=7, featured=True),
        ]
        db.session.add_all(sample_products)
        db.session.commit()


# ─── Store Routes ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    categories = Category.query.order_by(Category.sort_order).all()
    featured = Product.query.filter_by(featured=True, in_stock=True).limit(8).all()
    featured_bundles = Bundle.query.filter_by(featured=True, in_stock=True).all()
    return render_template('store/index.html', categories=categories, featured=featured,
                           featured_bundles=featured_bundles)


@app.route('/shop')
def shop():
    categories = Category.query.order_by(Category.sort_order).all()
    cat_slug = request.args.get('category', '')
    search = request.args.get('q', '').strip()
    query = Product.query.filter_by(in_stock=True)
    active_cat = None
    if cat_slug:
        active_cat = Category.query.filter_by(slug=cat_slug).first()
        if active_cat:
            query = query.filter_by(category_id=active_cat.id)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    products = query.order_by(Product.created_at.desc()).all()
    bundles = Bundle.query.filter_by(in_stock=True).order_by(Bundle.created_at.desc()).all() \
        if not active_cat and not search else []
    return render_template('store/shop.html', products=products, categories=categories,
                           active_cat=active_cat, search=search, bundles=bundles)


@app.route('/product/<int:pid>')
def product_detail(pid):
    product = Product.query.get_or_404(pid)
    related = Product.query.filter_by(category_id=product.category_id, in_stock=True)\
                           .filter(Product.id != pid).limit(4).all()
    complementary = Product.query.filter(
        Product.category_id != product.category_id,
        Product.in_stock == True,
        Product.featured == True
    ).limit(3).all()
    reviews = Review.query.filter_by(product_id=pid, approved=True)\
                          .order_by(Review.created_at.desc()).all()
    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None
    return render_template('store/product.html', product=product, related=related,
                           complementary=complementary, reviews=reviews, avg_rating=avg_rating)


@app.route('/bundle/<int:bid>')
def bundle_detail(bid):
    bundle = Bundle.query.get_or_404(bid)
    return render_template('store/bundle.html', bundle=bundle)


@app.route('/product/<int:pid>/review', methods=['POST'])
def submit_review(pid):
    Product.query.get_or_404(pid)
    name = request.form.get('customer_name', '').strip()
    try:
        rating = int(request.form.get('rating', 0))
    except ValueError:
        rating = 0
    comment = request.form.get('comment', '').strip()
    if not name or not 1 <= rating <= 5:
        flash('Please provide your name and a star rating.', 'error')
        return redirect(url_for('product_detail', pid=pid))
    db.session.add(Review(product_id=pid, customer_name=name,
                          rating=rating, comment=comment))
    db.session.commit()
    flash('Thank you! Your review will appear after approval.', 'success')
    return redirect(url_for('product_detail', pid=pid))


@app.route('/cart')
def cart():
    return render_template('store/cart.html')


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        cart_data = request.form.get('cart_data', '[]')
        try:
            items = json.loads(cart_data)
        except Exception:
            flash('Invalid cart data.', 'error')
            return redirect(url_for('cart'))
        if not items:
            flash('Your cart is empty.', 'error')
            return redirect(url_for('cart'))
        subtotal = sum(i['price'] * i['qty'] for i in items)
        # 10% bundle discount per category when 3+ items from same category
        from collections import defaultdict
        cat_qty = defaultdict(int)
        cat_sub = defaultdict(float)
        for i in items:
            cat_qty[i.get('cat', '')] += i['qty']
            cat_sub[i.get('cat', '')] += i['price'] * i['qty']
        bundle_savings = sum(
            cat_sub[c] * 0.10 for c, q in cat_qty.items() if q >= 3
        )
        discounted = subtotal - bundle_savings
        zone = request.form.get('zone', '').strip().lower()
        if discounted >= 2500:
            delivery = 0
        elif zone == 'dhaka':
            delivery = 70
        elif zone == 'sub-urban':
            delivery = 100
        else:
            delivery = 130
        total = discounted + delivery
        order = Order(
            customer_name=request.form['name'],
            customer_email=request.form['email'],
            customer_phone=request.form['phone'],
            address=request.form['address'],
            city=request.form['city'],
            items_json=json.dumps(items),
            total=total,
            notes=request.form.get('notes', '')
        )
        db.session.add(order)
        db.session.commit()
        notify_slack_order(order, items)
        return redirect(url_for('order_success', oid=order.id))
    return render_template('store/checkout.html')


@app.route('/about')
def about():
    return render_template('store/about.html')


@app.route('/order-success/<int:oid>')
def order_success(oid):
    order = Order.query.get_or_404(oid)
    return render_template('store/order_success.html', order=order)


# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    error = None
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if hashlib.sha256(pw.encode()).hexdigest() == ADMIN_PASSWORD_HASH:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        error = 'Wrong password. Try again.'
    return render_template('admin/login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    total_products = Product.query.count()
    total_orders   = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    revenue        = db.session.query(db.func.sum(Order.total)).scalar() or 0
    status_filter  = request.args.get('status', '')
    q = Order.query.filter_by(status=status_filter) if status_filter else Order.query
    orders = q.order_by(Order.created_at.desc()).limit(15).all()
    status_counts = {s: Order.query.filter_by(status=s).count()
                     for s in ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')}
    return render_template('admin/dashboard.html',
                           total_products=total_products,
                           total_orders=total_orders,
                           pending_orders=pending_orders,
                           revenue=revenue,
                           orders=orders,
                           status_filter=status_filter,
                           status_counts=status_counts)


@app.route('/admin/products')
@admin_required
def admin_products():
    categories = Category.query.order_by(Category.sort_order).all()
    cat_id = request.args.get('cat', type=int)
    if cat_id:
        products = Product.query.filter_by(category_id=cat_id).order_by(Product.name).all()
    else:
        products = Product.query.order_by(Product.category_id, Product.name).all()
    return render_template('admin/products.html', products=products, categories=categories, cat_id=cat_id)


@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    categories = Category.query.order_by(Category.sort_order).all()
    if request.method == 'POST':
        image_filename = save_uploaded_image(request.files.get('image'))
        orig = request.form.get('original_price', '').strip()
        product = Product(
            name=request.form['name'],
            description=request.form.get('description', ''),
            price=float(request.form['price']),
            original_price=float(orig) if orig else None,
            image=image_filename,
            category_id=int(request.form['category_id']),
            in_stock=bool(request.form.get('in_stock')),
            featured=bool(request.form.get('featured')),
            ingredients=request.form.get('ingredients', ''),
            weight=request.form.get('weight', ''),
        )
        db.session.add(product)
        db.session.commit()
        flash(f'"{product.name}" added successfully!', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', product=None, categories=categories)


@app.route('/admin/products/edit/<int:pid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(pid):
    product = Product.query.get_or_404(pid)
    categories = Category.query.order_by(Category.sort_order).all()
    if request.method == 'POST':
        f = request.files.get('image')
        if f and f.filename:
            new_image = save_uploaded_image(f)
            if new_image:
                delete_uploaded_image(product.image)
                product.image = new_image
        orig = request.form.get('original_price', '').strip()
        product.name = request.form['name']
        product.description = request.form.get('description', '')
        product.price = float(request.form['price'])
        product.original_price = float(orig) if orig else None
        product.category_id = int(request.form['category_id'])
        product.in_stock = bool(request.form.get('in_stock'))
        product.featured = bool(request.form.get('featured'))
        product.ingredients = request.form.get('ingredients', '')
        product.weight = request.form.get('weight', '')
        db.session.commit()
        flash(f'"{product.name}" updated successfully!', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', product=product, categories=categories)


@app.route('/admin/products/delete/<int:pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    product = Product.query.get_or_404(pid)
    delete_uploaded_image(product.image)
    name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f'"{name}" deleted.', 'success')
    return redirect(url_for('admin_products'))


@app.route('/admin/orders')
@admin_required
def admin_orders():
    status = request.args.get('status', '')
    query = Order.query
    if status:
        query = query.filter_by(status=status)
    orders = query.order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', orders=orders, status=status)


@app.route('/admin/orders/<int:oid>')
@admin_required
def admin_order_detail(oid):
    order = Order.query.get_or_404(oid)
    return render_template('admin/order_detail.html', order=order)


@app.route('/admin/orders/<int:oid>/status', methods=['POST'])
@admin_required
def admin_update_order_status(oid):
    order = Order.query.get_or_404(oid)
    order.status = request.form['status']
    db.session.commit()
    flash('Order status updated.', 'success')
    return redirect(url_for('admin_order_detail', oid=oid))


@app.route('/admin/reviews')
@admin_required
def admin_reviews():
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    return render_template('admin/reviews.html', reviews=reviews)


@app.route('/admin/reviews/<int:rid>/approve', methods=['POST'])
@admin_required
def admin_approve_review(rid):
    review = Review.query.get_or_404(rid)
    review.approved = not review.approved
    db.session.commit()
    flash('Review ' + ('approved.' if review.approved else 'hidden.'), 'success')
    return redirect(url_for('admin_reviews'))


@app.route('/admin/reviews/<int:rid>/delete', methods=['POST'])
@admin_required
def admin_delete_review(rid):
    review = Review.query.get_or_404(rid)
    db.session.delete(review)
    db.session.commit()
    flash('Review deleted.', 'success')
    return redirect(url_for('admin_reviews'))


@app.route('/admin/categories')
@admin_required
def admin_categories():
    categories = Category.query.order_by(Category.sort_order).all()
    return render_template('admin/categories.html', categories=categories)


@app.route('/admin/categories/add', methods=['POST'])
@admin_required
def admin_add_category():
    name = request.form['name'].strip()
    icon = request.form.get('icon', '🌿').strip()
    slug = name.lower().replace(' ', '-').replace('&', 'and')
    if not Category.query.filter_by(slug=slug).first():
        cat = Category(name=name, slug=slug, icon=icon,
                       sort_order=Category.query.count() + 1)
        db.session.add(cat)
        db.session.commit()
        flash(f'Category "{name}" added.', 'success')
    else:
        flash('Category already exists.', 'error')
    return redirect(url_for('admin_categories'))


@app.route('/admin/categories/delete/<int:cid>', methods=['POST'])
@admin_required
def admin_delete_category(cid):
    cat = Category.query.get_or_404(cid)
    if cat.products:
        flash('Cannot delete: category has products.', 'error')
    else:
        db.session.delete(cat)
        db.session.commit()
        flash(f'Category "{cat.name}" deleted.', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/bundles')
@admin_required
def admin_bundles():
    bundles = Bundle.query.order_by(Bundle.created_at.desc()).all()
    return render_template('admin/bundles.html', bundles=bundles)


def _products_data():
    products = Product.query.order_by(Product.name).all()
    return [{
        'id': p.id, 'name': p.name, 'price': p.price,
        'image': p.image, 'category': p.category.name, 'weight': p.weight,
    } for p in products]


def _parse_bundle_items(raw_json):
    try:
        raw_items = json.loads(raw_json or '[]')
    except (TypeError, ValueError):
        raw_items = []
    items = []
    for entry in raw_items:
        try:
            pid = int(entry['product_id'])
            qty = max(1, int(entry['qty']))
        except (KeyError, TypeError, ValueError):
            continue
        product = Product.query.get(pid)
        if product:
            items.append((product, qty))
    return items


@app.route('/admin/bundles/add', methods=['GET', 'POST'])
@admin_required
def admin_add_bundle():
    if request.method == 'POST':
        items = _parse_bundle_items(request.form.get('items_json'))
        if not items:
            flash('Select at least one product for the bundle.', 'error')
            return render_template('admin/bundle_form.html', bundle=None,
                                   products=_products_data(), selected_items=[])
        image_filename = save_uploaded_image(request.files.get('image'))
        original_price = sum(p.price * qty for p, qty in items)
        bundle = Bundle(
            name=request.form['name'],
            description=request.form.get('description', ''),
            price=float(request.form['price']),
            original_price=original_price,
            image=image_filename,
            in_stock=bool(request.form.get('in_stock')),
            featured=bool(request.form.get('featured')),
            is_deal=bool(request.form.get('is_deal')),
        )
        db.session.add(bundle)
        db.session.flush()
        for product, qty in items:
            db.session.add(BundleItem(bundle_id=bundle.id, product_id=product.id, quantity=qty))
        db.session.commit()
        flash(f'Bundle "{bundle.name}" created successfully!', 'success')
        return redirect(url_for('admin_bundles'))
    return render_template('admin/bundle_form.html', bundle=None,
                           products=_products_data(), selected_items=[])


@app.route('/admin/bundles/edit/<int:bid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_bundle(bid):
    bundle = Bundle.query.get_or_404(bid)
    if request.method == 'POST':
        items = _parse_bundle_items(request.form.get('items_json'))
        if not items:
            flash('Select at least one product for the bundle.', 'error')
            selected_items = [{'product_id': bi.product_id, 'qty': bi.quantity} for bi in bundle.items]
            return render_template('admin/bundle_form.html', bundle=bundle,
                                   products=_products_data(), selected_items=selected_items)
        f = request.files.get('image')
        if f and f.filename:
            new_image = save_uploaded_image(f)
            if new_image:
                delete_uploaded_image(bundle.image)
                bundle.image = new_image
        bundle.name = request.form['name']
        bundle.description = request.form.get('description', '')
        bundle.price = float(request.form['price'])
        bundle.original_price = sum(p.price * qty for p, qty in items)
        bundle.in_stock = bool(request.form.get('in_stock'))
        bundle.featured = bool(request.form.get('featured'))
        bundle.is_deal = bool(request.form.get('is_deal'))
        BundleItem.query.filter_by(bundle_id=bundle.id).delete()
        for product, qty in items:
            db.session.add(BundleItem(bundle_id=bundle.id, product_id=product.id, quantity=qty))
        db.session.commit()
        flash(f'Bundle "{bundle.name}" updated successfully!', 'success')
        return redirect(url_for('admin_bundles'))
    selected_items = [{'product_id': bi.product_id, 'qty': bi.quantity} for bi in bundle.items]
    return render_template('admin/bundle_form.html', bundle=bundle,
                           products=_products_data(), selected_items=selected_items)


@app.route('/admin/bundles/delete/<int:bid>', methods=['POST'])
@admin_required
def admin_delete_bundle(bid):
    bundle = Bundle.query.get_or_404(bid)
    delete_uploaded_image(bundle.image)
    name = bundle.name
    db.session.delete(bundle)
    db.session.commit()
    flash(f'Bundle "{name}" deleted.', 'success')
    return redirect(url_for('admin_bundles'))


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'change_password':
            new_pw = request.form.get('new_password', '').strip()
            confirm_pw = request.form.get('confirm_password', '').strip()
            if len(new_pw) < 6:
                flash('Password must be at least 6 characters.', 'error')
            elif new_pw != confirm_pw:
                flash('Passwords do not match.', 'error')
            else:
                # In a real app this would persist; here we just acknowledge
                flash('Password updated successfully! Update ADMIN_PASSWORD_HASH in app.py to make it permanent.', 'success')
        elif action == 'upload_logo':
            f = request.files.get('logo')
            if f and f.filename and f.filename.lower().endswith('.png'):
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], 'logo.png'))
                flash('Logo updated! It may take a moment to show up everywhere due to browser caching.', 'success')
            else:
                flash('Please upload a PNG file.', 'error')
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_categories = Category.query.count()
    db_label = 'PostgreSQL (Supabase)' if os.environ.get('DATABASE_URL') else 'SQLite (bohubrihi.db)'
    logo_exists = os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'logo.png'))
    return render_template('admin/settings.html',
                           total_products=total_products,
                           total_orders=total_orders,
                           total_categories=total_categories,
                           db_label=db_label,
                           logo_exists=logo_exists)


with app.app_context():
    db.create_all()
    seed_data()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
