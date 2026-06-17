from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.platypus import Image as RLImage
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
import json, os, random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sail-crm-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sail_crm_proj.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(30), nullable=False)
    full_name = db.Column(db.String(120))

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_code = db.Column(db.String(20), unique=True)
    company_name = db.Column(db.String(200), nullable=False)
    customer_type = db.Column(db.String(30))
    gst_number = db.Column(db.String(20))
    pan_number = db.Column(db.String(15))
    contact_person = db.Column(db.String(100))
    designation = db.Column(db.String(80))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    city = db.Column(db.String(60))
    state = db.Column(db.String(60))
    registration_date = db.Column(db.Date, default=date.today)
    assigned_executive = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Active')
    rpi_score = db.Column(db.Float, default=50.0)
    is_manual_override = db.Column(db.Boolean, default=False)
    orders = db.relationship('Order', backref='customer', lazy=True)
    payments = db.relationship('Payment', backref='customer', lazy=True)
    orders = db.relationship('Order', backref='customer', lazy=True)
    payments = db.relationship('Payment', backref='customer', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_code = db.Column(db.String(20), unique=True)
    product_name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80))
    steel_grade = db.Column(db.String(80))
    plant_origin = db.Column(db.String(20))
    thickness_mm = db.Column(db.String(50))
    width_mm = db.Column(db.String(50))
    length_m = db.Column(db.String(50))
    process_flags = db.Column(db.String(200))
    unit = db.Column(db.String(20), default='Tonnes')
    base_price = db.Column(db.Float)
    available_stock = db.Column(db.Float, default=0)

class Quotation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quote_number = db.Column(db.String(20), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    customer = db.relationship('Customer', backref='quotations')
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    product = db.relationship('Product')
    quantity = db.Column(db.Float)
    unit_price = db.Column(db.Float)
    gst_percent = db.Column(db.Float, default=18.0)
    subtotal = db.Column(db.Float)
    gst_amount = db.Column(db.Float)
    total_amount = db.Column(db.Float)
    remarks = db.Column(db.Text)
    status = db.Column(db.String(20), default='Draft')
    created_date = db.Column(db.Date, default=date.today)
    items = db.relationship('QuotationItem', backref='quotation', lazy=True, cascade='all, delete-orphan')

class QuotationItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.Integer, db.ForeignKey('quotation.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product = db.relationship('Product')
    quantity = db.Column(db.Float)
    unit_price = db.Column(db.Float)
    subtotal = db.Column(db.Float)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product = db.relationship('Product')
    quantity = db.Column(db.Float)
    order_value = db.Column(db.Float)
    order_date = db.Column(db.Date, default=date.today)
    delivery_date = db.Column(db.Date)
    dispatch_date = db.Column(db.Date)
    status = db.Column(db.String(30), default='Pending')

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(20), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    invoice_amount = db.Column(db.Float)
    due_date = db.Column(db.Date)
    payment_date = db.Column(db.Date)
    outstanding_amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='Pending')

class MarketSupport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    customer = db.relationship('Customer')
    period = db.Column(db.String(20))
    market_condition = db.Column(db.String(20))  # Bull, Stable, Bear
    expected_purchase = db.Column(db.Float)
    actual_purchase = db.Column(db.Float)
    support_rating = db.Column(db.String(20))  # Excellent, Good, Average, Poor
    notes = db.Column(db.Text)
    recorded_date = db.Column(db.Date, default=date.today)

# Auth
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() or request.form
        user = User.query.filter_by(username=data.get('username')).first()
        if user and check_password_hash(user.password_hash, data.get('password')):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['full_name'] = user.full_name
            if request.is_json:
                return jsonify({'success': True, 'role': user.role})
            return redirect(url_for('dashboard'))
        if request.is_json:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    full_name = data.get('full_name')

    # Check if user already exists
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Username already exists. Please choose another.'}), 400

    # Create new user (defaulting to 'executive' role for safety)
    new_user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role='executive',
        full_name=full_name
    )

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Registration successful! You can now sign in.'})

# Pages
@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/customers')
@login_required
def customers_page():
    return render_template('customers.html')

@app.route('/products')
@login_required
def products_page():
    return render_template('products.html')

@app.route('/quotations')
@login_required
def quotations_page():
    return render_template('quotations.html')

@app.route('/orders')
@login_required
def orders_page():
    return render_template('orders.html')

@app.route('/payments')
@login_required
def payments_page():
    return render_template('payments.html')

@app.route('/rpi')
@login_required
def rpi_page():
    return render_template('rpi.html')

@app.route('/customer/<int:cid>/profile')
@login_required
def customer_profile(cid):
    return render_template('customer_profile.html', customer_id=cid)

# API: Dashboard
@app.route('/api/dashboard')
@login_required
def api_dashboard():
    total_customers = Customer.query.filter_by(status='Active').count()
    total_orders = Order.query.count()
    total_revenue = db.session.query(db.func.sum(Order.order_value)).scalar() or 0
    outstanding = db.session.query(db.func.sum(Payment.outstanding_amount)).scalar() or 0
    total_quotations = Quotation.query.count()

    # Monthly revenue (last 6 months)
    monthly = []
    today = date.today()
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        m_start = date(y, m, 1)
        if m == 12:
            m_end = date(y + 1, 1, 1)
        else:
            m_end = date(y, m + 1, 1)

        rev = db.session.query(db.func.sum(Order.order_value)).filter(
            Order.order_date >= m_start, Order.order_date < m_end
        ).scalar() or 0
        monthly.append({'month': m_start.strftime('%b %Y'), 'revenue': round(rev/1e7, 2)})

    # Top customers
    top_customers = db.session.query(
        Customer.company_name,
        db.func.sum(Order.order_value).label('total')
    ).join(Order).group_by(Customer.id).order_by(db.desc('total')).limit(5).all()

    # RPI distribution
    rpi_dist = {
        'Platinum': Customer.query.filter(Customer.rpi_score >= 85).count(),
        'Gold': Customer.query.filter(Customer.rpi_score >= 70, Customer.rpi_score < 85).count(),
        'Silver': Customer.query.filter(Customer.rpi_score >= 50, Customer.rpi_score < 70).count(),
        'General': Customer.query.filter(Customer.rpi_score < 50).count(),
    }

    # Order status
    order_status = {}
    for s in ['Pending', 'Processing', 'Dispatched', 'Delivered']:
        order_status[s] = Order.query.filter_by(status=s).count()

    return jsonify({
        'kpis': {
            'total_customers': total_customers,
            'total_orders': total_orders,
            'total_revenue': round(total_revenue / 1e7, 2),
            'outstanding': round(outstanding / 1e5, 2),
            'total_quotations': total_quotations,
        },
        'monthly_revenue': monthly,
        'top_customers': [{'name': r[0], 'value': round(r[1]/1e7, 2)} for r in top_customers],
        'rpi_distribution': rpi_dist,
        'order_status': order_status,
    })

# API: Customers
@app.route('/api/customers', methods=['GET'])
@login_required
def api_customers():
    q = request.args.get('q', '')
    ctype = request.args.get('type', '')
    query = Customer.query
    if q:
        query = query.filter(Customer.company_name.ilike(f'%{q}%') | Customer.contact_person.ilike(f'%{q}%'))
    if ctype:
        query = query.filter_by(customer_type=ctype)
    customers = query.order_by(Customer.company_name).all()
    return jsonify([{
        'id': c.id, 'customer_code': c.customer_code, 'company_name': c.company_name,
        'customer_type': c.customer_type, 'contact_person': c.contact_person,
        'email': c.email, 'phone': c.phone, 'city': c.city, 'state': c.state,
        'status': c.status, 'rpi_score': c.rpi_score,
        'rpi_category': rpi_category(c.rpi_score)
    } for c in customers])

@app.route('/api/customers', methods=['POST'])
@login_required
def api_add_customer():
    d = request.get_json()
    count = Customer.query.count() + 1
    c = Customer(
        customer_code=f'SAIL-C{count:04d}',
        company_name=d['company_name'], customer_type=d.get('customer_type'),
        gst_number=d.get('gst_number'), pan_number=d.get('pan_number'),
        contact_person=d.get('contact_person'), designation=d.get('designation'),
        email=d.get('email'), phone=d.get('phone'), address=d.get('address'),
        city=d.get('city'), state=d.get('state'),
        assigned_executive=d.get('assigned_executive'), status='Active', rpi_score=50.0
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({'success': True, 'id': c.id})

@app.route('/api/customers/<int:cid>', methods=['GET'])
@login_required
def api_get_customer(cid):
    c = Customer.query.get_or_404(cid)
    orders = Order.query.filter_by(customer_id=cid).all()
    payments = Payment.query.filter_by(customer_id=cid).all()
    total_revenue = sum(o.order_value for o in orders)
    paid = sum(p.invoice_amount - p.outstanding_amount for p in payments)
    outstanding = sum(p.outstanding_amount for p in payments)
    on_time = sum(1 for p in payments if p.payment_date and p.due_date and p.payment_date <= p.due_date)

    return jsonify({
        'id': c.id, 'customer_code': c.customer_code, 'company_name': c.company_name,
        'customer_type': c.customer_type, 'gst_number': c.gst_number,
        'pan_number': c.pan_number, 'contact_person': c.contact_person,
        'designation': c.designation, 'email': c.email, 'phone': c.phone,
        'address': c.address, 'city': c.city, 'state': c.state,
        'registration_date': str(c.registration_date), 'assigned_executive': c.assigned_executive,
        'status': c.status, 'rpi_score': c.rpi_score, 'rpi_category': rpi_category(c.rpi_score),
        'stats': {
            'total_orders': len(orders), 'total_revenue': total_revenue,
            'paid': paid, 'outstanding': outstanding,
            'on_time_payments': on_time, 'total_payments': len(payments)
        },
        'recent_orders': [{
            'order_number': o.order_number, 'product': o.product.product_name,
            'quantity': o.quantity, 'order_value': o.order_value,
            'order_date': str(o.order_date), 'status': o.status
        } for o in orders[-5:]]
    })

@app.route('/api/customers/<int:cid>', methods=['PUT'])
@login_required
def api_update_customer(cid):
    c = Customer.query.get_or_404(cid)
    d = request.get_json()
    for field in ['company_name','customer_type','contact_person','designation',
                  'email','phone','address','city','state','status','assigned_executive']:
        if field in d:
            setattr(c, field, d[field])
    db.session.commit()
    return jsonify({'success': True})

# API: Products
@app.route('/api/products', methods=['GET'])
@login_required
def api_products():
    products = Product.query.all()
    return jsonify([{
        'id': p.id, 'product_code': p.product_code, 'product_name': p.product_name,
        'category': p.category, 'steel_grade': p.steel_grade, 'plant_origin': p.plant_origin,
        'thickness_mm': p.thickness_mm, 'width_mm': p.width_mm,
        'process_flags': p.process_flags, 'unit': p.unit,
        'base_price': p.base_price, 'available_stock': p.available_stock
    } for p in products])

@app.route('/api/products', methods=['POST'])
@login_required
def api_add_product():
    d = request.get_json()
    count = Product.query.count() + 1
    p = Product(
        product_code=f'SAIL-P{count:04d}',
        product_name=d['product_name'], category=d.get('category'),
        steel_grade=d.get('steel_grade'), plant_origin=d.get('plant_origin'),
        thickness_mm=d.get('thickness_mm'), width_mm=d.get('width_mm'),
        length_m=d.get('length_m'), process_flags=d.get('process_flags'),
        unit=d.get('unit', 'Tonnes'), base_price=float(d.get('base_price', 0)),
        available_stock=float(d.get('available_stock', 0))
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({'success': True, 'id': p.id})

# API: Quotations
@app.route('/api/quotations', methods=['GET'])
@login_required
def api_quotations():
    quotes = Quotation.query.join(Customer).order_by(Customer.company_name, Quotation.created_date.desc()).all()
    return jsonify([{
        'id': q.id,
        'quote_number': q.quote_number,
        'customer_name': q.customer.company_name,
        'item_count': len(q.items) or (1 if q.product_id else 0),
        'item_summary': q.items[0].product.product_name if q.items else (q.product.product_name if q.product else '–'),
        'products': [{
            'product_name': item.product.product_name,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'subtotal': item.subtotal
        } for item in q.items] if q.items else [{
            'product_name': q.product.product_name if q.product else '–',
            'quantity': q.quantity,
            'unit_price': q.unit_price,
            'subtotal': q.subtotal
        }],
        'total_amount': q.total_amount,
        'status': q.status,
        'created_date': str(q.created_date)
    } for q in quotes])

@app.route('/api/quotations', methods=['POST'])
@login_required
def api_create_quotation():
    d = request.get_json()
    items = d.get('items', []) or []
    if not items:
        return jsonify({'success': False, 'message': 'Quotation must contain at least one item.'}), 400

    count = Quotation.query.count() + 1
    gst = float(d.get('gst_percent', 18))
    first = items[0]
    quote = Quotation(
        quote_number=f'QT-{date.today().year}-{count:04d}',
        customer_id=int(d['customer_id']),
        product_id=int(first['product_id']),
        quantity=float(first.get('quantity', 0)),
        unit_price=float(first.get('unit_price', 0)),
        gst_percent=gst,
        subtotal=0.0,
        gst_amount=0.0,
        total_amount=0.0,
        remarks=d.get('remarks', ''),
        status='Draft'
    )
    db.session.add(quote)
    db.session.flush()

    subtotal = 0.0
    for item in items:
        qty = float(item.get('quantity', 0))
        price = float(item.get('unit_price', 0))
        line_subtotal = qty * price
        subtotal += line_subtotal
        qi = QuotationItem(
            quotation_id=quote.id,
            product_id=int(item['product_id']),
            quantity=qty,
            unit_price=price,
            subtotal=line_subtotal
        )
        db.session.add(qi)

    quote.subtotal = subtotal
    gst_amt = subtotal * gst / 100
    quote.gst_amount = gst_amt
    quote.total_amount = subtotal + gst_amt
    db.session.commit()
    return jsonify({'success': True, 'id': quote.id, 'quote_number': quote.quote_number})

@app.route('/api/quotations/<int:qid>/status', methods=['PUT'])
@login_required
def api_update_quote_status(qid):
    q = Quotation.query.get_or_404(qid)
    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status:
        q.status = new_status
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Missing status field'}), 400

# API: Orders
@app.route('/api/orders', methods=['GET'])
@login_required
def api_orders():
    orders = Order.query.order_by(Order.order_date.desc()).all()
    return jsonify([{
        'id': o.id, 'order_number': o.order_number,
        'customer_name': o.customer.company_name,
        'product_name': o.product.product_name,
        'quantity': o.quantity, 'order_value': o.order_value,
        'order_date': str(o.order_date),
        'delivery_date': str(o.delivery_date) if o.delivery_date else None,
        'status': o.status
    } for o in orders])

@app.route('/api/orders', methods=['POST'])
@login_required
def api_create_order():
    d = request.get_json()
    count = Order.query.count() + 1
    o = Order(
        order_number=f'ORD-{date.today().year}-{count:04d}',
        customer_id=int(d['customer_id']), product_id=int(d['product_id']),
        quantity=float(d['quantity']), order_value=float(d['order_value']),
        delivery_date=datetime.strptime(d['delivery_date'], '%Y-%m-%d').date() if d.get('delivery_date') else None,
        status='Pending'
    )
    db.session.add(o)
    db.session.commit()
    return jsonify({'success': True, 'id': o.id})

@app.route('/api/orders/<int:oid>/status', methods=['PUT'])
@login_required
def api_update_order_status(oid):
    o = Order.query.get_or_404(oid)
    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status:
        o.status = new_status
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Missing status field'}), 400

# API: Payments
@app.route('/api/payments', methods=['GET'])
@login_required
def api_payments():
    payments = Payment.query.order_by(Payment.due_date.desc()).all()
    result = []
    for p in payments:
        delay = 0
        if p.payment_date and p.due_date:
            delay = (p.payment_date - p.due_date).days
        result.append({
            'id': p.id, 'invoice_number': p.invoice_number,
            'customer_name': p.customer.company_name,
            'invoice_amount': p.invoice_amount,
            'due_date': str(p.due_date) if p.due_date else None,
            'payment_date': str(p.payment_date) if p.payment_date else None,
            'outstanding_amount': p.outstanding_amount,
            'status': p.status, 'delay_days': delay
        })
    return jsonify(result)

@app.route('/api/payments/<int:pid>/record', methods=['PUT'])
@login_required
def api_record_payment(pid):
    p = Payment.query.get_or_404(pid)
    d = request.get_json()
    p.payment_date = datetime.strptime(d['payment_date'], '%Y-%m-%d').date()
    p.outstanding_amount = float(d.get('outstanding_amount', 0))
    p.status = 'Paid' if p.outstanding_amount == 0 else 'Partial'
    db.session.commit()
    return jsonify({'success': True})

# API: RPI
@app.route('/api/rpi', methods=['GET'])
@login_required
def api_rpi():
    customers = Customer.query.filter_by(status='Active').order_by(Customer.rpi_score.desc()).all()
    return jsonify([{
        'id': c.id, 'company_name': c.company_name,
        'rpi_score': c.rpi_score, 'category': rpi_category(c.rpi_score),
        'customer_type': c.customer_type
    } for c in customers])

@app.route('/api/rpi/<int:cid>', methods=['GET'])
@login_required
def api_rpi_detail(cid):
    c = Customer.query.get_or_404(cid)
    # Automatically recalculates and saves to keep it fresh
    score, vol, pay, loy, mkt, mut, ms = update_customer_rpi(cid)

    return jsonify({
        'customer_name': c.company_name, 'rpi_score': score,
        'category': rpi_category(score),
        'components': {
            'volume_score': round(vol, 1),
            'payment_score': round(pay, 1),
            'loyalty_score': round(loy, 1),
            'market_support_score': round(mkt, 1),
            'mutual_support_score': round(mut, 1),
        },
        'market_support_records': [{
            'period': m.period, 'market_condition': m.market_condition,
            'expected': m.expected_purchase, 'actual': m.actual_purchase,
            'rating': m.support_rating
        } for m in ms]
    })
@app.route('/api/market_support', methods=['POST'])
@login_required
def api_add_market_support():
    d = request.get_json()
    ms = MarketSupport(
        customer_id=int(d['customer_id']),
        period=d['period'], market_condition=d['market_condition'],
        expected_purchase=float(d['expected_purchase']),
        actual_purchase=float(d['actual_purchase']),
        support_rating=d['support_rating'], notes=d.get('notes', '')
    )
    db.session.add(ms)
    db.session.commit()

    # Instantly update this specific customer's score when new data is added
    update_customer_rpi(int(d['customer_id']))

    return jsonify({'success': True})

# Helper

# Helper to recalculate and save RPI
def update_customer_rpi(cid):
    c = Customer.query.get(cid)
    if not c: return

    orders = Order.query.filter_by(customer_id=cid).all()
    payments = Payment.query.filter_by(customer_id=cid).all()
    ms = MarketSupport.query.filter_by(customer_id=cid).all()

    # Volume score (25)
    total_rev = sum(o.order_value for o in orders)
    vol_score = min(25, total_rev / 1e8 * 25)

    # Payment score (20)
    if payments:
        on_time = sum(1 for p in payments if p.payment_date and p.due_date and p.payment_date <= p.due_date)
        pay_score = min(20, (on_time / len(payments)) * 20)
    else:
        pay_score = 10

    # Loyalty score (15) - based on years
    years = (date.today() - c.registration_date).days / 365 if c.registration_date else 0
    loyalty_score = min(15, years * 2)

    # Market support score (20)
    if ms:
        rating_map = {'Excellent': 4, 'Good': 3, 'Average': 2, 'Poor': 1}
        avg = sum(rating_map.get(m.support_rating, 2) for m in ms) / len(ms)
        market_score = min(20, avg * 5)
    else:
        market_score = 10

    # Mutual support score (20)
    mutual_score = 10

    total = vol_score + pay_score + loyalty_score + market_score + mutual_score
    if not c.is_manual_override:
        c.rpi_score = round(total, 1)
        db.session.commit()

    return c.rpi_score, vol_score, pay_score, loyalty_score, market_score, mutual_score, ms

def rpi_category(score):
    if score >= 85: return 'Platinum'
    if score >= 70: return 'Gold'
    if score >= 50: return 'Silver'
    return 'General'

# PDF Generation
def generate_quotation_pdf(quotation_id):
    """Generate PDF for a quotation"""
    q = Quotation.query.get_or_404(quotation_id)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1e3a5f'),
        spaceAfter=6, fontName='Helvetica-Bold'
    )
    heading_style = ParagraphStyle(
        'CustomHeading', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#1a6eb5'),
        spaceAfter=4, fontName='Helvetica-Bold'
    )
    normal_style = ParagraphStyle(
        'CustomNormal', parent=styles['Normal'], fontSize=10, spaceAfter=3
    )

    # Header
    header_data = [['SAIL CRM - QUOTATION', '', 'Quote #: ' + q.quote_number],
                   ['Steel Authority of India Ltd', '', f'Date: {q.created_date}']]
    header_table = Table(header_data, colWidths=[2.5*inch, 1.5*inch, 2*inch])
    header_table.setStyle(TableStyle([
        ('FONT', (0, 0), (0, 1), 'Helvetica-Bold', 12),
        ('FONT', (2, 0), (2, 1), 'Helvetica', 10),
        ('ALIGN', (2, 0), (2, 1), 'RIGHT'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*inch))

    # Customer Details
    elements.append(Paragraph('Bill To:', heading_style))
    cust_data = [
        ['Company:', q.customer.company_name],
        ['Contact:', q.customer.contact_person],
        ['Phone:', q.customer.phone],
        ['Email:', q.customer.email],
        ['GST No:', q.customer.gst_number],
    ]
    cust_table = Table(cust_data, colWidths=[1.5*inch, 4*inch])
    cust_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(cust_table)
    elements.append(Spacer(1, 0.2*inch))

    # Line Items
    elements.append(Paragraph('Line Items:', heading_style))
    line_data = [['Product', 'Qty', 'Unit', 'Base Price/T', 'Unit Price', 'Amount']]
    if q.items:
        for item in q.items:
            line_data.append([
                item.product.product_name[:30],
                str(item.quantity),
                'Tonnes',
                f"₹{item.product.base_price:,.0f}",
                f"₹{item.unit_price:,.0f}",
                f"₹{item.subtotal:,.0f}"
            ])
    else:
        line_data.append([
            q.product.product_name[:30] if q.product else '–',
            str(q.quantity or 0),
            'Tonnes',
            f"₹{q.product.base_price:,.0f}" if q.product and q.product.base_price else '₹0',
            f"₹{q.unit_price:,.0f}",
            f"₹{q.subtotal:,.0f}"
        ])
    line_table = Table(line_data, colWidths=[2.1*inch, 0.7*inch, 0.7*inch, 1*inch, 1*inch, 1*inch])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, 1), 'LEFT'),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 0.2*inch))

    # Summary
    summary_data = [
        ['Subtotal:', '', f"₹{q.subtotal:,.2f}"],
        [f'GST ({q.gst_percent}%):', '', f"₹{q.gst_amount:,.2f}"],
        ['Total Amount:', '', f"₹{q.total_amount:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[3*inch, 1*inch, 1.5*inch])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('FONT', (0, 0), (-1, -2), 'Helvetica', 9),
        ('FONT', (0, 2), (-1, 2), 'Helvetica-Bold', 11),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#e8500a')),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.white),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3*inch))

    # Status & Notes
    elements.append(Paragraph(f'<b>Status:</b> {q.status}', normal_style))
    if q.remarks:
        elements.append(Paragraph(f'<b>Remarks:</b> {q.remarks[:100]}...', normal_style))

    # Footer
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph('Thank you for your business!', ParagraphStyle(
        'Footer', parent=styles['Normal'], alignment=TA_CENTER, fontSize=9, textColor=colors.grey
    )))

    doc.build(elements)
    buffer.seek(0)
    return buffer

def generate_order_pdf(order_id):
    """Generate PDF for an order"""
    o = Order.query.get_or_404(order_id)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1e3a5f'),
        spaceAfter=6, fontName='Helvetica-Bold'
    )
    heading_style = ParagraphStyle(
        'CustomHeading', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#1a6eb5'),
        spaceAfter=4, fontName='Helvetica-Bold'
    )

    # Header
    header_data = [['SAIL CRM - ORDER CONFIRMATION', '', f'Order #: {o.order_number}'],
                   ['Steel Authority of India Ltd', '', f'Date: {o.order_date}']]
    header_table = Table(header_data, colWidths=[2.5*inch, 1.5*inch, 2*inch])
    header_table.setStyle(TableStyle([
        ('FONT', (0, 0), (0, 1), 'Helvetica-Bold', 12),
        ('FONT', (2, 0), (2, 1), 'Helvetica', 10),
        ('ALIGN', (2, 0), (2, 1), 'RIGHT'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*inch))

    # Customer Details
    elements.append(Paragraph('Ship To:', heading_style))
    cust_data = [
        ['Customer:', o.customer.company_name],
        ['Contact:', o.customer.contact_person],
        ['Address:', o.customer.address or 'N/A'],
        ['City/State:', f"{o.customer.city}, {o.customer.state}"],
    ]
    cust_table = Table(cust_data, colWidths=[1.5*inch, 4*inch])
    cust_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(cust_table)
    elements.append(Spacer(1, 0.2*inch))

    # Order Details
    elements.append(Paragraph('Order Details:', heading_style))
    detail_data = [
        ['Product:', o.product.product_name],
        ['Quantity:', f"{o.quantity} Tonnes"],
        ['Order Value:', f"₹{o.order_value:,.2f}"],
        ['Delivery Date:', str(o.delivery_date) if o.delivery_date else 'TBD'],
        ['Status:', o.status],
    ]
    detail_table = Table(detail_data, colWidths=[1.5*inch, 4*inch])
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f4f8')),
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    elements.append(detail_table)
    elements.append(Spacer(1, 0.3*inch))

    # Footer
    elements.append(Paragraph('Order Terms & Conditions apply. Please refer to the sales agreement for full details.',
                             ParagraphStyle('Footer', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8, textColor=colors.grey)))

    doc.build(elements)
    buffer.seek(0)
    return buffer

def generate_invoice_pdf(payment_id):
    """Generate PDF for an invoice/payment"""
    p = Payment.query.get_or_404(payment_id)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1e3a5f'),
        spaceAfter=6, fontName='Helvetica-Bold'
    )
    heading_style = ParagraphStyle(
        'CustomHeading', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#1a6eb5'),
        spaceAfter=4, fontName='Helvetica-Bold'
    )

    # Header
    header_data = [['SAIL CRM - INVOICE', '', f'Invoice #: {p.invoice_number}'],
                   ['Steel Authority of India Ltd', '', f'Issued: {date.today()}']]
    header_table = Table(header_data, colWidths=[2.5*inch, 1.5*inch, 2*inch])
    header_table.setStyle(TableStyle([
        ('FONT', (0, 0), (0, 1), 'Helvetica-Bold', 12),
        ('FONT', (2, 0), (2, 1), 'Helvetica', 10),
        ('ALIGN', (2, 0), (2, 1), 'RIGHT'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*inch))

    # Bill To
    elements.append(Paragraph('Bill To:', heading_style))
    cust_data = [
        ['Company:', p.customer.company_name],
        ['Contact:', p.customer.phone],
        ['Email:', p.customer.email],
        ['GST No:', p.customer.gst_number],
    ]
    cust_table = Table(cust_data, colWidths=[1.5*inch, 4*inch])
    cust_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(cust_table)
    elements.append(Spacer(1, 0.2*inch))

    # Invoice Details
    elements.append(Paragraph('Invoice Details:', heading_style))
    inv_data = [
        ['Invoice Amount:', f"₹{p.invoice_amount:,.2f}"],
        ['Due Date:', str(p.due_date) if p.due_date else 'N/A'],
        ['Payment Date:', str(p.payment_date) if p.payment_date else 'Pending'],
        ['Outstanding Amount:', f"₹{p.outstanding_amount:,.2f}"],
        ['Status:', p.status],
    ]
    inv_table = Table(inv_data, colWidths=[1.5*inch, 4*inch])
    inv_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f4f8')),
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    elements.append(inv_table)
    elements.append(Spacer(1, 0.3*inch))

    # Summary Box
    summary_data = [
        ['Total Due:', f"₹{p.invoice_amount:,.2f}"],
        ['Paid:', f"₹{p.invoice_amount - p.outstanding_amount:,.2f}"],
        ['Balance Due:', f"₹{p.outstanding_amount:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[3*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (1, -1), 'RIGHT'),
        ('FONT', (0, 0), (-1, -2), 'Helvetica', 9),
        ('FONT', (0, 2), (-1, 2), 'Helvetica-Bold', 11),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#16a34a')),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.white),
    ]))
    elements.append(summary_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# PDF Download Endpoints
@app.route('/quotations/<int:qid>/pdf')
@login_required
def download_quotation_pdf(qid):
    pdf_buffer = generate_quotation_pdf(qid)
    return send_file(pdf_buffer, mimetype='application/pdf',
                    as_attachment=True, download_name=f'quotation_{qid}.pdf')

@app.route('/orders/<int:oid>/pdf')
@login_required
def download_order_pdf(oid):
    pdf_buffer = generate_order_pdf(oid)
    return send_file(pdf_buffer, mimetype='application/pdf',
                    as_attachment=True, download_name=f'order_{oid}.pdf')

@app.route('/payments/<int:pid>/pdf')
@login_required
def download_invoice_pdf(pid):
    pdf_buffer = generate_invoice_pdf(pid)
    return send_file(pdf_buffer, mimetype='application/pdf',
                    as_attachment=True, download_name=f'invoice_{pid}.pdf')

# Seed data
def seed_data():
    if User.query.count() > 0:
        return
    users = [
        User(username='admin', password_hash=generate_password_hash('admin123'), role='admin', full_name='Admin User'),
        User(username='manager', password_hash=generate_password_hash('manager123'), role='manager', full_name='Arin Kumar'),
        User(username='exec1', password_hash=generate_password_hash('exec123'), role='executive', full_name='Priya Sharma'),
    ]
    db.session.add_all(users)

    products = [
        Product(product_code='SAIL-P0001', product_name='Long Rails (260m)', category='Rails',
                steel_grade='IRS-T12 Grade 880', plant_origin='BSP',
                length_m='Up to 260', process_flags='Head Hardened', unit='Tonnes', base_price=68000, available_stock=5200),
        Product(product_code='SAIL-P0002', product_name='Seismic TMT Fe 500S', category='TMT Bars',
                steel_grade='Fe 500S', plant_origin='BSP',
                thickness_mm='8-40', process_flags='Thermo-Mechanically Treated', unit='Tonnes', base_price=56000, available_stock=12000),
        Product(product_code='SAIL-P0003', product_name='TMCP Plates (High Strength)', category='Plates',
                steel_grade='IS 2062 E450', plant_origin='RSP',
                thickness_mm='6-100', width_mm='1500-3500', process_flags='TMCP Applied', unit='Tonnes', base_price=72000, available_stock=3800),
        Product(product_code='SAIL-P0004', product_name='Hot Rolled Coils', category='Coils',
                steel_grade='IS 10748', plant_origin='RSP',
                thickness_mm='1.2-25.4', width_mm='700-1850', process_flags='Hot Strip Mill', unit='Tonnes', base_price=58000, available_stock=8500),
        Product(product_code='SAIL-P0005', product_name='Cold Rolled Coils (Deep Draw)', category='Coils',
                steel_grade='IS 513 CR4', plant_origin='BSL',
                thickness_mm='0.35-3.15', width_mm='700-1550', process_flags='CRM III, RH Degassed', unit='Tonnes', base_price=78000, available_stock=4200),
        Product(product_code='SAIL-P0006', product_name='LPG Cylinder Steel', category='Plates',
                steel_grade='IS 15914', plant_origin='BSL',
                thickness_mm='2.0-3.5', process_flags='RH Degassed, LD Converter', unit='Tonnes', base_price=82000, available_stock=2100),
        Product(product_code='SAIL-P0007', product_name='Slabs (Continuous Cast)', category='Semis',
                steel_grade='IS 2002', plant_origin='BSP',
                thickness_mm='200-250', width_mm='900-1850', process_flags='Continuous Cast', unit='Tonnes', base_price=42000, available_stock=18000),
        Product(product_code='SAIL-P0008', product_name='Structural Sections (Wide Flange)', category='Structurals',
                steel_grade='IS 2062 E250', plant_origin='ISP',
                thickness_mm='Various', process_flags='Hot Rolled', unit='Tonnes', base_price=61000, available_stock=6700),
    ]
    db.session.add_all(products)

    cust_data = [
        ('Tata Projects Ltd', 'Project', 'Rajiv Mehta', 'GM Procurement', 'rajiv@tataprojects.com', '9811234567', 'Mumbai', 'Maharashtra', 92.5, 'exec1', date(2018, 3, 15)),
        ('JSW Infrastructure', 'Consumer', 'Anand Sharma', 'Director Purchase', 'anand@jswinfra.com', '9822345678', 'Gurgaon', 'Haryana', 87.3, 'exec1', date(2019, 6, 20)),
        ('Steel Trading Corp', 'Trader', 'Mohan Das', 'Proprietor', 'mohan@steeltrading.com', '9833456789', 'Kolkata', 'West Bengal', 74.1, 'exec1', date(2020, 1, 10)),
        ('L&T Construction', 'Project', 'Suresh Pillai', 'VP Procurement', 'suresh@lnt.com', '9844567890', 'Chennai', 'Tamil Nadu', 81.6, 'exec1', date(2019, 9, 5)),
        ('BHEL Fabrication', 'Consumer', 'Deepak Singh', 'Sr. Manager', 'deepak@bhel.com', '9855678901', 'Hyderabad', 'Telangana', 68.2, 'exec1', date(2020, 11, 22)),
        ('Rungta Steel Pvt Ltd', 'Trader', 'Vikram Rungta', 'MD', 'vikram@rungta.com', '9866789012', 'Raipur', 'Chhattisgarh', 55.4, 'exec1', date(2021, 4, 3)),
        ('NMDC Limited', 'Consumer', 'Arun Mishra', 'AGM Materials', 'arun@nmdc.com', '9877890123', 'Hyderabad', 'Telangana', 78.9, 'exec1', date(2019, 7, 18)),
        ('Gammon India', 'Project', 'Pradeep Joshi', 'Purchase Manager', 'pradeep@gammon.com', '9888901234', 'Pune', 'Maharashtra', 44.7, 'exec1', date(2022, 2, 14)),
    ]
    customers = []
    for i, (name, ctype, cp, des, email, ph, city, state, rpi, exec_, reg) in enumerate(cust_data, 1):
        c = Customer(
            customer_code=f'SAIL-C{i:04d}', company_name=name, customer_type=ctype,
            gst_number=f'27AAA{i:04d}C1Z5', pan_number=f'AAAC{i:04d}C',
            contact_person=cp, designation=des, email=email, phone=ph,
            city=city, state=state, rpi_score=rpi, assigned_executive=exec_,
            status='Active', registration_date=reg
        )
        customers.append(c)
        db.session.add(c)
    db.session.flush()

    # Orders & Payments
    order_count = 1
    pay_count = 1
    statuses = ['Delivered', 'Dispatched', 'Processing', 'Pending']
    for c in customers:
        for j in range(random.randint(3, 8)):
            prod = random.choice(products)
            qty = round(random.uniform(50, 500), 1)
            val = round(qty * prod.base_price * random.uniform(0.97, 1.03))
            od = date.today() - timedelta(days=random.randint(10, 400))
            dd = od + timedelta(days=random.randint(14, 45))
            o = Order(
                order_number=f'ORD-2024-{order_count:04d}',
                customer_id=c.id, product_id=prod.id,
                quantity=qty, order_value=val, order_date=od, delivery_date=dd,
                status=random.choice(statuses)
            )
            db.session.add(o)
            order_count += 1

            # Payment for older orders
            if od < date.today() - timedelta(days=30):
                due = od + timedelta(days=30)
                delay = random.randint(-10, 20)
                paid_date = due + timedelta(days=delay)
                outstanding = 0 if delay < 15 else round(val * 0.2)
                p = Payment(
                    invoice_number=f'INV-2024-{pay_count:04d}',
                    customer_id=c.id, invoice_amount=val,
                    due_date=due, payment_date=paid_date,
                    outstanding_amount=outstanding,
                    status='Paid' if outstanding == 0 else 'Partial'
                )
                db.session.add(p)
                pay_count += 1

    # Market support records
    conditions = ['Bull', 'Stable', 'Bear']
    ratings = ['Excellent', 'Good', 'Average', 'Poor']
    for c in customers[:5]:
        for yr in ['2022-H1', '2022-H2', '2023-H1', '2023-H2']:
            cond = random.choice(conditions)
            exp = round(random.uniform(500, 3000))
            act = round(exp * random.uniform(0.6, 1.2))
            ms = MarketSupport(
                customer_id=c.id, period=yr, market_condition=cond,
                expected_purchase=exp, actual_purchase=act,
                support_rating=random.choice(ratings)
            )
            db.session.add(ms)

    # Quotations
    q_statuses = ['Draft', 'Sent', 'Approved', 'Rejected']
    for i in range(1, 15):
        c = random.choice(customers)
        item_count = random.randint(1, 3)
        quote = Quotation(
            quote_number=f'QT-2024-{i:04d}',
            customer_id=c.id,
            gst_percent=18,
            status=random.choice(q_statuses),
            created_date=date.today() - timedelta(days=random.randint(1, 90))
        )
        db.session.add(quote)
        db.session.flush()
        subtotal = 0.0
        for j in range(item_count):
            p = random.choice(products)
            qty = round(random.uniform(20, 300), 1)
            price = p.base_price * random.uniform(0.98, 1.05)
            line_total = round(qty * price)
            subtotal += line_total
            qi = QuotationItem(
                quotation_id=quote.id,
                product_id=p.id,
                quantity=qty,
                unit_price=round(price),
                subtotal=line_total
            )
            db.session.add(qi)
        gst = subtotal * 0.18
        quote.subtotal = round(subtotal)
        quote.gst_amount = round(gst)
        quote.total_amount = round(subtotal + gst)

    db.session.commit()

    # Calculate the true RPI score for everyone based on the generated orders
    for c in Customer.query.all():
        update_customer_rpi(c.id)

    print("Seed data loaded")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True, port=5000)
