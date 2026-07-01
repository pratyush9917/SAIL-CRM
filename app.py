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
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
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
    status = db.Column(db.String(30), default='Active')
    rpi_score = db.Column(db.Float, nullable=True) # Now allows NO score
    is_manual_override = db.Column(db.Boolean, default=False)
    
    # --- NEW: Inquiry & Onboarding Fields ---
    is_new_inquiry = db.Column(db.Boolean, default=False)
    project_location = db.Column(db.String(200))
    req_material = db.Column(db.String(100))
    req_grade = db.Column(db.String(80))
    req_qty = db.Column(db.Float)
    
    # --- NEW: Document Checklist ---
    doc_gst = db.Column(db.Boolean, default=False)
    doc_kyc = db.Column(db.Boolean, default=False)
    doc_pan = db.Column(db.Boolean, default=False)
    doc_work_order = db.Column(db.Boolean, default=False)

    orders = db.relationship('Order', backref='customer', lazy=True)
    payments = db.relationship('Payment', backref='customer', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
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
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
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
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_number = db.Column(db.String(20), unique=True)
    po_number = db.Column(db.String(50))
    quotation_id = db.Column(db.Integer, db.ForeignKey('quotation.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product = db.relationship('Product')
    quantity = db.Column(db.Float)
    dispatched_quantity = db.Column(db.Float, default=0.0)
    order_value = db.Column(db.Float)
    order_date = db.Column(db.Date, default=date.today)
    delivery_date = db.Column(db.Date)
    dispatch_date = db.Column(db.Date)
    status = db.Column(db.String(30), default='Pending')

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    invoice_number = db.Column(db.String(20), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    invoice_amount = db.Column(db.Float)
    due_date = db.Column(db.Date)
    payment_date = db.Column(db.Date)
    outstanding_amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='Pending')

class MarketSupport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
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

@app.route('/api/users', methods=['POST'])
@login_required
def api_create_user():
    # STRICT EXECUTIVE LOCK
    if session.get('role') != 'executive':
        return jsonify({'success': False, 'message': 'Permission Denied: Only Executives can add new members.'}), 403

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    full_name = data.get('full_name')
    role = data.get('role', 'executive') # Default to executive if none provided

    # Check if user already exists
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Username already exists. Please choose another.'}), 400

    new_user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        full_name=full_name
    )

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'success': True, 'message': f'New {role} added successfully!'})

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
    query = Customer.query.filter_by(owner_id=session['user_id'])
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
        'rpi_category': rpi_category(c.rpi_score),
        # Pass document status to the frontend
        'doc_gst': c.doc_gst, 'doc_kyc': c.doc_kyc, 
        'doc_pan': c.doc_pan, 'doc_work_order': c.doc_work_order
    } for c in customers])

@app.route('/api/customers/<int:cid>/approve', methods=['PUT'])
@login_required
def api_approve_customer(cid):
    c = Customer.query.get_or_404(cid)
    
    # Optional security: Ensure only executives or admins can approve
    # if session.get('role') not in ['executive', 'admin', 'manager']:
    #     return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if c.status == 'Pending Approval':
        c.status = 'Active' # Changes them to a fully active trading customer
        db.session.commit()
        return jsonify({'success': True})
        
    return jsonify({'success': False, 'message': 'Customer is not ready for approval'}), 400

@app.route('/api/customers', methods=['POST'])
@login_required
def api_add_customer():
    d = request.get_json()
    count = Customer.query.count() + 1
    
    # Determine Initial Status based on the workflow
    is_new = d.get('is_new_inquiry', False)
    if is_new:
        # Check if all required docs are checked
        if d.get('doc_gst') and d.get('doc_kyc') and d.get('doc_pan') and d.get('doc_work_order'):
            initial_status = 'Pending Approval'
        else:
            initial_status = 'Documents Missing'
    else:
        initial_status = 'Active' # Legacy/Old customer bypass
        
    c = Customer(
        owner_id=session['user_id'],
        customer_code=f'SAIL-C{count:04d}',
        company_name=d['company_name'], customer_type=d.get('customer_type'),
        gst_number=d.get('gst_number'), pan_number=d.get('pan_number'),
        contact_person=d.get('contact_person'), designation=d.get('designation'),
        email=d.get('email'), phone=d.get('phone'), address=d.get('address'),
        city=d.get('city'), state=d.get('state'),
        assigned_executive=d.get('assigned_executive'), 
        status=initial_status, 
        rpi_score=50.0,
        
        # New Fields
        is_new_inquiry=is_new,
        project_location=d.get('project_location'),
        req_material=d.get('req_material'),
        req_grade=d.get('req_grade'),
        req_qty=float(d.get('req_qty', 0)) if d.get('req_qty') else None,
        doc_gst=d.get('doc_gst', False),
        doc_kyc=d.get('doc_kyc', False),
        doc_pan=d.get('doc_pan', False),
        doc_work_order=d.get('doc_work_order', False)
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({'success': True, 'id': c.id})

@app.route('/api/customers/<int:cid>', methods=['GET'])
@login_required
def api_get_customer(cid):
    c = Customer.query.filter_by(id=cid, owner_id=session['user_id']).first_or_404()
    orders = Order.query.filter_by(customer_id=cid, owner_id=session['user_id']).all()
    payments = Payment.query.filter_by(customer_id=cid, owner_id=session['user_id']).all()
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
    products = Product.query.filter_by(owner_id=session['user_id']).all()
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
        owner_id=session['user_id'],
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

@app.route('/api/products/<int:pid>/stock', methods=['PUT'])
@login_required
def api_update_product_stock(pid):
    p = Product.query.get_or_404(pid)
    data = request.get_json()
    
    if 'available_stock' in data:
        p.available_stock = float(data['available_stock'])
        db.session.commit()
        return jsonify({'success': True})
        
    return jsonify({'success': False, 'message': 'Missing stock value'}), 400

# API: Quotations
@app.route('/api/quotations', methods=['GET'])
@login_required
def api_quotations():
    quotes = Quotation.query.join(Customer)\
        .filter(Quotation.owner_id == session['user_id'])\
        .order_by(Customer.company_name, Quotation.created_date.desc())\
        .all()
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
        owner_id=session['user_id'],
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
def api_update_quotation_status(qid):
    q = Quotation.query.get_or_404(qid)
    data = request.get_json() or {}
    new_status = data.get('status')
    
    if new_status:
        q.status = new_status
        db.session.commit()
        return jsonify({'success': True})
        
    return jsonify({'success': False, 'message': 'Missing status field'}), 400

@app.route('/api/orders/<int:oid>/status', methods=['PUT'])
@login_required
def api_update_order_status(oid):
    o = Order.query.get_or_404(oid)
    data = request.get_json() or {}
    new_status = data.get('status')
    force_partial = data.get('force_partial', False)
    
    if new_status:
        # THE PAYMENT LOCK & PROPORTIONAL DISPATCH
        if new_status in ['Dispatched', 'Lifted', 'Delivered']:
            payments = Payment.query.filter_by(customer_id=o.customer_id).all()
            total_invoiced = sum(p.invoice_amount for p in payments)
            total_outstanding = sum(p.outstanding_amount for p in payments)
            
            if total_outstanding > 0:
                # Calculate the percentage paid and the allowed tonnage
                paid_ratio = (total_invoiced - total_outstanding) / total_invoiced if total_invoiced > 0 else 0
                allowed_qty = round(o.quantity * paid_ratio, 2)
                
                if allowed_qty <= 0:
                    return jsonify({
                        'success': False, 
                        'message': f'{new_status.upper()} BLOCKED: 0% payment received. 100% advance required.'
                    }), 403
                    
                if not force_partial:
                    # Throw the intercept back to the frontend to ask for Executive Approval
                    return jsonify({
                        'success': False, 
                        'requires_approval': True,
                        'message': f'Customer has outstanding payments. Proportional release allowed: {allowed_qty} Tonnes.'
                    }), 403
                else:
                    # STRICT EXECUTIVE LOCK: Only 'executive' role can approve
                    if session.get('role') != 'executive':
                        return jsonify({'success': False, 'message': 'Permission Denied: Only Executives can approve partial releases.'}), 403
                    
                    o.dispatched_quantity = allowed_qty
                    o.status = 'Partially Dispatched' # Keeps it accurately flagged as partial
                    db.session.commit()
                    return jsonify({'success': True})

        # If fully paid or moving to other open statuses
        if new_status in ['Dispatched', 'Lifted', 'Delivered']:
            o.dispatched_quantity = o.quantity # They paid for it, they get everything
            
        o.status = new_status
        db.session.commit()
        return jsonify({'success': True})
        
    return jsonify({'success': False, 'message': 'Missing status field'}), 400


@app.route('/api/orders', methods=['GET'])
@login_required
def api_orders():
    orders = Order.query.filter_by(owner_id=session['user_id']).order_by(Order.order_number.asc()).all()
    
    return jsonify([{
        'id': o.id, 'order_number': o.order_number,
        'po_number': o.po_number, # <--- Make sure this is here!
        'customer_name': o.customer.company_name,
        'product_name': o.product.product_name,
        'base_price': o.product.base_price,
        'quantity': o.quantity, 'order_value': get_order_display_value(o),
        'dispatched_quantity': o.dispatched_quantity,
        'order_date': str(o.order_date),
        'delivery_date': str(o.delivery_date) if o.delivery_date else None,
        'status': o.status
    } for o in orders])

@app.route('/api/orders', methods=['POST'])
@login_required
def api_create_order():
    d = request.get_json()
    count = Order.query.count() + 1
    delivery_date = datetime.strptime(d['delivery_date'], '%Y-%m-%d').date() if d.get('delivery_date') else None
    
    o = Order(
        owner_id=session['user_id'],
        order_number=f'ORD-{date.today().year}-{count:04d}',
        po_number=d.get('po_number'),
        customer_id=int(d['customer_id']), product_id=int(d['product_id']),
        quantity=float(d['quantity']), order_value=float(d['order_value']),
        delivery_date=delivery_date,
        status='Pending'
    )
    db.session.add(o)
    db.session.flush() # Saves the order to generate its ID immediately
    
    # --- NEW: AUTO-GENERATE PAYMENT INVOICE ---
    p = Payment(
        invoice_number=o.order_number.replace('ORD', 'INV'), # Links INV number to ORD number
        customer_id=o.customer_id,
        invoice_amount=calculate_invoice_total(o.order_value, 18.0),
        due_date=delivery_date or (date.today() + timedelta(days=30)),
        outstanding_amount=calculate_invoice_total(o.order_value, 18.0),
        status='Pending'
    )
    db.session.add(p)
    # ------------------------------------------
    
    db.session.commit()
    return jsonify({'success': True, 'id': o.id})

@app.route('/api/orders/<int:oid>/delivery', methods=['PUT'])
@login_required
def api_update_order_delivery(oid):
    o = Order.query.get_or_404(oid)
    data = request.get_json() or {}
    new_date = data.get('delivery_date')
    
    if new_date:
        o.delivery_date = datetime.strptime(new_date, '%Y-%m-%d').date()
        db.session.commit()
        return jsonify({'success': True})
        
    return jsonify({'success': False, 'message': 'Missing delivery date'}), 400

@app.route('/api/orders/from_quotation', methods=['POST'])
@login_required
def api_create_order_from_quotation():
    d = request.get_json()
    quote_id = d.get('quotation_id')
    delivery_date_str = d.get('delivery_date')
    po_number = d.get('po_number')

    if not quote_id:
        return jsonify({'success': False, 'message': 'Quotation ID required'}), 400

    q = Quotation.query.get_or_404(int(quote_id))
    
    if q.status != 'Approved':
        return jsonify({'success': False, 'message': 'Only Approved quotations can be ordered.'}), 400

    delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date() if delivery_date_str else None

    # Loop through the items on the quote and generate an Order & Payment for each
    if q.items:
        for item in q.items:
            count = Order.query.count() + 1
            o = Order(
                owner_id=session['user_id'],
                order_number=f'ORD-{date.today().year}-{count:04d}',
                po_number=po_number,
                quotation_id=q.id,
                customer_id=q.customer_id,
                product_id=item.product_id,
                quantity=item.quantity,
                order_value=item.subtotal,
                delivery_date=delivery_date,
                status='Pending'
            )
            db.session.add(o)
            db.session.flush()
            
            # Auto-generate payment
            p = Payment(
                owner_id=session['user_id'],
                invoice_number=o.order_number.replace('ORD', 'INV'),
                customer_id=o.customer_id,
                invoice_amount=calculate_invoice_total(o.order_value, q.gst_percent or 18.0),
                due_date=delivery_date or (date.today() + timedelta(days=30)),
                outstanding_amount=calculate_invoice_total(o.order_value, q.gst_percent or 18.0),
                status='Pending'
            )
            db.session.add(p)
    else:
        # Fallback for old quotes without line items
        count = Order.query.count() + 1
        o = Order(
            order_number=f'ORD-{date.today().year}-{count:04d}',
            customer_id=q.customer_id,
            product_id=q.product_id,
            quantity=q.quantity,
            order_value=q.total_amount,
            delivery_date=delivery_date,
            status='Pending'
        )
        db.session.add(o)
        db.session.flush()
        
        # Auto-generate payment
        p = Payment(
            invoice_number=o.order_number.replace('ORD', 'INV'),
            customer_id=o.customer_id,
            invoice_amount=calculate_invoice_total(o.order_value, q.gst_percent or 18.0),
            due_date=delivery_date or (date.today() + timedelta(days=30)),
            outstanding_amount=calculate_invoice_total(o.order_value, q.gst_percent or 18.0),
            status='Pending'
        )
        db.session.add(p)

    q.status = 'Ordered'
    db.session.commit()
    return jsonify({'success': True})@app.route('/api/orders/<int:oid>', methods=['DELETE'])

@app.route('/api/orders/<int:oid>', methods=['DELETE'])
@login_required
def api_delete_order(oid):
    o = Order.query.get_or_404(oid)
    
    # --- CASCADE DELETE THE PAYMENT ---
    inv_number = o.order_number.replace('ORD', 'INV')
    payment = Payment.query.filter_by(invoice_number=inv_number).first()
    
    if payment:
        db.session.delete(payment)
        
    # --- NEW: AUTO-REVERT QUOTATION ---
    if o.quotation_id:
        # Check if this is the last order linked to this quotation
        remaining = Order.query.filter_by(quotation_id=o.quotation_id).count()
        if remaining <= 1:
            q = Quotation.query.get(o.quotation_id)
            if q and q.status == 'Ordered':
                q.status = 'Approved' # Unlocks the quote!
        
    # Now delete the order itself
    db.session.delete(o)
    db.session.commit()
    return jsonify({'success': True})

# API: Payments
@app.route('/api/payments', methods=['GET'])
@login_required
def api_payments():
    payments = Payment.query.filter_by(owner_id=session['user_id']).order_by(Payment.due_date.desc()).all()
    result = []
    for p in payments:
        delay = 0
        if p.payment_date and p.due_date:
            delay = (p.payment_date - p.due_date).days
        invoice_amount, outstanding_amount = get_payment_display_amounts(p)
        result.append({
            'id': p.id, 
            'invoice_number': p.invoice_number,
            'order_number': p.invoice_number.replace('INV', 'ORD'), # <--- DERIVES THE ORDER NUMBER
            'customer_name': p.customer.company_name,
            'invoice_amount': invoice_amount,
            'due_date': str(p.due_date) if p.due_date else None,
            'payment_date': str(p.payment_date) if p.payment_date else None,
            'outstanding_amount': outstanding_amount,
            'status': p.status, 'delay_days': delay
        })
    return jsonify(result)
def sync_order_dispatch_from_payment(payment):
    if not payment:
        return None

    order_number = None
    if payment.invoice_number:
        order_number = payment.invoice_number.replace('INV', 'ORD', 1)

    order = Order.query.filter_by(order_number=order_number).first() if order_number else None
    if not order:
        return None

    if payment.outstanding_amount <= 0:
        order.dispatched_quantity = order.quantity or 0
        if order.status not in ['Delivered', 'Lifted']:
            order.status = 'Dispatched'
    return order


def get_payment_gst_percent(order=None):
    if order and order.quotation_id:
        quote = Quotation.query.get(order.quotation_id)
        if quote and quote.gst_percent is not None:
            return float(quote.gst_percent)
    return 18.0


def calculate_invoice_total(base_amount, gst_percent=18.0):
    base_amount = float(base_amount or 0)
    gst_percent = float(gst_percent or 0)
    return round(base_amount * (1 + gst_percent / 100), 2)


def get_order_gst_percent(order):
    if order and order.quotation_id:
        quote = Quotation.query.get(order.quotation_id)
        if quote and quote.gst_percent is not None:
            return float(quote.gst_percent)
    return 18.0


def get_order_display_value(order):
    if not order:
        return 0
    return calculate_invoice_total(order.order_value, get_order_gst_percent(order))


def get_payment_display_amounts(payment):
    order_number = None
    if payment.invoice_number:
        order_number = payment.invoice_number.replace('INV', 'ORD', 1)
    order = Order.query.filter_by(order_number=order_number).first() if order_number else None
    gst_percent = get_payment_gst_percent(order)

    invoice_base = float(payment.invoice_amount or 0)
    invoice_total = invoice_base
    if order and order.order_value:
        if invoice_base < float(order.order_value) * 1.1:
            invoice_total = calculate_invoice_total(invoice_base, gst_percent)
    else:
        invoice_total = calculate_invoice_total(invoice_base, gst_percent)

    outstanding_base = float(payment.outstanding_amount or 0)
    outstanding_total = outstanding_base
    if order and order.order_value:
        if invoice_base < float(order.order_value) * 1.1:
            outstanding_total = calculate_invoice_total(outstanding_base, gst_percent)
    else:
        outstanding_total = calculate_invoice_total(outstanding_base, gst_percent)

    return round(invoice_total, 2), round(outstanding_total, 2)

@app.route('/api/payments/<int:pid>/record', methods=['PUT'])
@login_required
def api_record_payment(pid):
    p = Payment.query.get_or_404(pid)
    d = request.get_json()
    p.payment_date = datetime.strptime(d['payment_date'], '%Y-%m-%d').date()
    p.outstanding_amount = float(d.get('outstanding_amount', 0))
    p.status = 'Paid' if p.outstanding_amount == 0 else 'Partial'

    sync_order_dispatch_from_payment(p)
    db.session.commit()
    return jsonify({'success': True})

# API: RPI
@app.route('/api/rpi', methods=['GET'])
@login_required
def api_rpi():
    customers = Customer.query.filter_by(status='Active', owner_id=session['user_id']).order_by(Customer.rpi_score.desc()).all()
    return jsonify([{
        'id': c.id, 'company_name': c.company_name,
        'rpi_score': c.rpi_score, 'category': rpi_category(c.rpi_score),
        'customer_type': c.customer_type
    } for c in customers])

@app.route('/api/rpi/<int:cid>', methods=['GET'])
@login_required
def api_rpi_detail(cid):
    c = Customer.query.filter_by(id=cid, owner_id=session['user_id']).first_or_404()
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
        owner_id=session['user_id'],
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

    # THE NEW RULE: No data? No RPI score.
    if not orders and not payments and not ms:
        if not c.is_manual_override:
            c.rpi_score = None
            db.session.commit()
        return None, 0, 0, 0, 0, 0, ms

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
    if score is None: return 'Pending Data'
    if score >= 85: return 'Platinum'
    if score >= 70: return 'Gold'
    if score >= 50: return 'Silver'
    return 'General'

# --- NEW PAGES ---
@app.route('/sales-calendar')
@login_required
def sales_calendar_page():
    return render_template('sales_calendar.html')

@app.route('/net-sales')
@login_required
def net_sales_page():
    if session.get('role') != 'executive':
        return redirect(url_for('dashboard')) # Restrict to executives
    return render_template('net_sales.html')

# --- NEW APIs ---
@app.route('/api/sales_calendar')
@login_required
def api_sales_calendar():
    # Only fetch orders belonging to the logged-in user!
    orders = Order.query.filter_by(owner_id=session['user_id']).all()
    
    daily_sales = {}
    for o in orders:
        if o.order_date:
            d_str = o.order_date.strftime('%Y-%m-%d')
            daily_sales[d_str] = daily_sales.get(d_str, 0) + o.order_value

    # FY Calculation (April to March)
    today = date.today()
    fy_year = today.year if today.month >= 4 else today.year - 1
    fy_string = f"{fy_year}-{fy_year+1}"
    
    monthly = []
    for m in range(4, 16):
        calc_month = m if m <= 12 else m - 12
        calc_year = fy_year if m <= 12 else fy_year + 1
        
        m_start = date(calc_year, calc_month, 1)
        if calc_month == 12:
            m_end = date(calc_year + 1, 1, 1)
        else:
            m_end = date(calc_year, calc_month + 1, 1)

        rev = sum(o.order_value for o in orders if o.order_date and m_start <= o.order_date < m_end)
        monthly.append({'month': m_start.strftime('%b %Y'), 'revenue': rev})

    return jsonify({'daily': daily_sales, 'monthly': monthly, 'fy_string': fy_string})

@app.route('/api/net_sales')
@login_required
def api_net_sales():
    # If you want Managers/Admins to see this page too, you can delete the next two lines!
    if session.get('role') != 'executive':
        return jsonify({'success': False}), 403
        
    # FETCH ALL ORDERS ACROSS THE ENTIRE COMPANY
    orders = Order.query.all()
    
    total_sales = sum(o.order_value for o in orders)
    total_tonnage = sum(o.quantity for o in orders)
    net_profit = total_sales * 0.15 
    
    # We join with the User table here implicitly if you have a relationship setup, 
    # or we can just fetch the user to show who made the sale.
    recent_orders = []
    for o in sorted(orders, key=lambda x: x.order_date, reverse=True)[:10]:
        owner = User.query.get(o.owner_id)
        recent_orders.append({
            'order_number': o.order_number,
            'customer': o.customer.company_name,
            'executive': owner.full_name if owner else 'Unknown', # NEW: Show who closed it
            'value': o.order_value,
            'date': str(o.order_date)
        })
    
    return jsonify({
        'total_sales': total_sales,
        'total_tonnage': total_tonnage,
        'net_profit': net_profit,
        'recent_orders': recent_orders
    })

# --- NEW PAGE: Sales Forecast ---
@app.route('/sales-forecast')
@login_required
def sales_forecast_page():
    return render_template('sales_forecast.html')

# --- NEW API: Sales Forecast Logic ---
@app.route('/api/sales_forecast')
@login_required
def api_sales_forecast():
    # Fetch orders based on role (Admin sees all, Exec sees their own)
    if session.get('role') in ['admin', 'manager']:
        orders = Order.query.all()
    else:
        orders = Order.query.filter_by(owner_id=session['user_id']).all()

    # Group sales by Year-Month (e.g., '2023-11': 500000)
    monthly_totals = {}
    for o in orders:
        if o.order_date:
            month_key = o.order_date.strftime('%Y-%m')
            monthly_totals[month_key] = monthly_totals.get(month_key, 0) + get_order_display_value(o)

    # Sort the months chronologically
    sorted_months = sorted(monthly_totals.keys())
    
    actual_sales = []
    forecast_sales = []
    labels = []

    # Calculate 3-Month Simple Moving Average (SMA)
    for i in range(len(sorted_months)):
        current_month = sorted_months[i]
        labels.append(current_month)
        actual_sales.append(monthly_totals[current_month])
        
        # We need at least 3 previous months to calculate the forecast
        if i >= 3:
            # Average of the last 3 months
            sma = (monthly_totals[sorted_months[i-1]] + 
                   monthly_totals[sorted_months[i-2]] + 
                   monthly_totals[sorted_months[i-3]]) / 3
            forecast_sales.append(round(sma, 2))
        else:
            # Not enough data to forecast, put 'null' for Chart.js
            forecast_sales.append(None)

    # Predict NEXT month (which hasn't happened yet)
    if len(sorted_months) >= 3:
        next_month_prediction = (actual_sales[-1] + actual_sales[-2] + actual_sales[-3]) / 3
        # Calculate growth/decline percentage
        trend_pct = ((next_month_prediction - actual_sales[-1]) / actual_sales[-1]) * 100 if actual_sales[-1] > 0 else 0
    else:
        next_month_prediction = 0
        trend_pct = 0

    return jsonify({
        'labels': labels,
        'actual': actual_sales,
        'forecast': forecast_sales,
        'next_month_prediction': next_month_prediction,
        'current_month_actual': actual_sales[-1] if actual_sales else 0,
        'trend_percentage': round(trend_pct, 1)
    })

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
                f"Rs. {item.product.base_price:,.0f}",
                f"Rs. {item.unit_price:,.0f}",
                f"Rs. {item.subtotal:,.0f}"
            ])
    else:
        line_data.append([
            q.product.product_name[:30] if q.product else '–',
            str(q.quantity or 0),
            'Tonnes',
            f"Rs. {q.product.base_price:,.0f}" if q.product and q.product.base_price else 'Rs. 0',
            f"Rs. {q.unit_price:,.0f}",
            f"Rs. {q.subtotal:,.0f}"
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
        ['Subtotal:', '', f"Rs. {q.subtotal:,.2f}"],
        [f'GST ({q.gst_percent}%):', '', f"Rs. {q.gst_amount:,.2f}"],
        ['Total Amount:', '', f"Rs. {q.total_amount:,.2f}"],
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
        ['Order Value:', f"Rs. {o.order_value:,.2f}"],
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
        ['Invoice Amount:', f"Rs. {p.invoice_amount:,.2f}"],
        ['Due Date:', str(p.due_date) if p.due_date else 'N/A'],
        ['Payment Date:', str(p.payment_date) if p.payment_date else 'Pending'],
        ['Outstanding Amount:', f"Rs. {p.outstanding_amount:,.2f}"],
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
        ['Total Due:', f"Rs. {p.invoice_amount:,.2f}"],
        ['Paid:', f"Rs. {p.invoice_amount - p.outstanding_amount:,.2f}"],
        ['Balance Due:', f"Rs. {p.outstanding_amount:,.2f}"],
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
    
    random.seed(42)

    # 1. Create Users
    users = [
        User(username='admin', password_hash=generate_password_hash('admin123'), role='admin', full_name='Admin User'),
        User(username='manager', password_hash=generate_password_hash('manager123'), role='manager', full_name='Arin Kumar'),
        User(username='exec1', password_hash=generate_password_hash('exec123'), role='executive', full_name='Priya Sharma'),
    ]
    db.session.add_all(users)
    db.session.flush() # Flush so every user gets their user.id assigned!

    # Base templates for data generation
    prod_templates = [
        ('Long Rails (260m)', 'Rails', 'IRS-T12 Grade 880', 'BSP', 'Up to 260', 'Head Hardened', 68000, 5200),
        ('Seismic TMT Fe 500S', 'TMT Bars', 'Fe 500S', 'BSP', '8-40', 'Thermo-Mechanically Treated', 56000, 12000),
        ('TMCP Plates (High Strength)', 'Plates', 'IS 2062 E450', 'RSP', '6-100', 'TMCP Applied', 72000, 3800),
        ('Hot Rolled Coils', 'Coils', 'IS 10748', 'RSP', '1.2-25.4', 'Hot Strip Mill', 58000, 8500),
        ('Cold Rolled Coils (Deep Draw)', 'Coils', 'IS 513 CR4', 'BSL', '0.35-3.15', 'CRM III, RH Degassed', 78000, 4200),
        ('LPG Cylinder Steel', 'Plates', 'IS 15914', 'BSL', '2.0-3.5', 'RH Degassed, LD Converter', 82000, 2100),
        ('Structural Sections (Wide Flange)', 'Structurals', 'IS 2062 E250', 'ISP', 'Various', 'Hot Rolled', 61000, 6700),
    ]

    cust_data = [
        ('Tata Projects Ltd', 'Project', 'Rajiv Mehta', 'GM Procurement', 'rajiv@tataprojects.com', '9811234567', 'Mumbai', 'Maharashtra', date(2018, 3, 15)),
        ('JSW Infrastructure', 'Consumer', 'Anand Sharma', 'Director Purchase', 'anand@jswinfra.com', '9822345678', 'Gurgaon', 'Haryana', date(2019, 6, 20)),
        ('Steel Trading Corp', 'Trader', 'Mohan Das', 'Proprietor', 'mohan@steeltrading.com', '9833456789', 'Kolkata', 'West Bengal', date(2020, 1, 10)),
        ('L&T Construction', 'Project', 'Suresh Pillai', 'VP Procurement', 'suresh@lnt.com', '9844567890', 'Chennai', 'Tamil Nadu', date(2019, 9, 5)),
        ('BHEL Fabrication', 'Consumer', 'Deepak Singh', 'Sr. Manager', 'deepak@bhel.com', '9855678901', 'Hyderabad', 'Telangana', date(2020, 11, 22)),
        ('Rungta Steel Pvt Ltd', 'Trader', 'Vikram Rungta', 'MD', 'vikram@rungta.com', '9866789012', 'Raipur', 'Chhattisgarh', date(2021, 4, 3)),
        ('NMDC Limited', 'Consumer', 'Arun Mishra', 'AGM Materials', 'arun@nmdc.com', '9877890123', 'Hyderabad', 'Telangana', date(2019, 7, 18)),
        ('Gammon India', 'Project', 'Pradeep Joshi', 'Purchase Manager', 'pradeep@gammon.com', '9888901234', 'Pune', 'Maharashtra', date(2022, 2, 14)),
    ]

    # 2. LOOP OVER EVERY USER TO GENERATE THEIR PRIVATE WORKSPACE
    for user in users:
        products = []
        for idx, (pname, cat, grade, plant, dim, flags, price, stock) in enumerate(prod_templates, 1):
            p = Product(
                owner_id=user.id,  # <-- STAMPED
                product_code=f'SAIL-P{user.id}-{idx:04d}',  # <-- UNIQUE PER USER
                product_name=pname, category=cat, steel_grade=grade, plant_origin=plant,
                process_flags=flags, unit='Tonnes', base_price=price, available_stock=stock
            )
            products.append(p)
            db.session.add(p)
        db.session.flush()

        customers = []
        for i, (name, ctype, cp, des, email, ph, city, state, reg) in enumerate(cust_data, 1):
            c = Customer(
                owner_id=user.id,  # <-- STAMPED
                customer_code=f'SAIL-C{user.id}-{i:04d}',  # <-- UNIQUE PER USER
                company_name=f"{name} ({user.username})",  # Visual tag so you know whose data it is
                customer_type=ctype,
                gst_number=f'27AAA{user.id}{i:03d}C1Z5', pan_number=f'AAAC{user.id}{i:03d}C',
                contact_person=cp, designation=des, email=email, phone=ph,
                city=city, state=state, assigned_executive=user.username,
                status='Active', registration_date=reg
            )
            customers.append(c)
            db.session.add(c)
        db.session.flush()

        order_count = 1
        pay_count = 1
        statuses = ['Delivered', 'Dispatched', 'Processing', 'Pending']
        
        for c in customers:
            for j in range(random.randint(3, 8)):
                prod = random.choice(products)
                qty = round(random.uniform(50, 500), 1)
                val = round(qty * prod.base_price * random.uniform(0.97, 1.03))
                od = date.today() - timedelta(days=random.randint(10, 350))
                dd = od + timedelta(days=random.randint(14, 45))
                disp_qty = qty if statuses[j % 4] in ['Delivered', 'Dispatched'] else 0.0
                fake_po = f"PO-{random.randint(10000, 99999)}" if random.random() > 0.2 else None
                
                o = Order(
                    owner_id=user.id,  # <-- STAMPED
                    order_number=f'ORD-2024-{user.id}-{order_count:04d}',  # <-- UNIQUE PER USER
                    po_number=fake_po, customer_id=c.id, product_id=prod.id,
                    quantity=qty, dispatched_quantity=disp_qty, order_value=val, order_date=od, delivery_date=dd,
                    status=statuses[j % 4]
                )
                db.session.add(o)
                db.session.flush() # Flush to get o.id
                order_count += 1

                # Payment for older orders
                if od < date.today() - timedelta(days=30):
                    due = od + timedelta(days=30)
                    delay = random.randint(-10, 20)
                    paid_date = due + timedelta(days=delay)
                    outstanding = 0 if delay < 15 else round(val * 0.2)
                    p = Payment(
                        owner_id=user.id,  # <-- STAMPED
                        invoice_number=f'INV-2024-{user.id}-{pay_count:04d}',
                        
                        customer_id=c.id, invoice_amount=val,
                        due_date=due, payment_date=paid_date,
                        outstanding_amount=outstanding,
                        status='Paid' if outstanding == 0 else 'Partial'
                    )
                    db.session.add(p)
                    pay_count += 1

        conditions = ['Bull', 'Stable', 'Bear']
        ratings = ['Excellent', 'Good', 'Average', 'Poor']
        for c in customers[:5]:
            for yr in ['2022-H1', '2022-H2', '2023-H1', '2023-H2']:
                cond = random.choice(conditions)
                exp = round(random.uniform(500, 3000))
                act = round(exp * random.uniform(0.6, 1.2))
                ms = MarketSupport(
                    owner_id=user.id,  # <-- STAMPED
                    customer_id=c.id, period=yr, market_condition=cond,
                    expected_purchase=exp, actual_purchase=act,
                    support_rating=random.choice(ratings)
                )
                db.session.add(ms)

        q_statuses = ['Draft', 'Sent', 'Approved', 'Rejected']
        for i in range(1, 15):
            c = random.choice(customers)
            item_count = random.randint(1, 3)
            quote = Quotation(
                owner_id=user.id,  # <-- STAMPED
                quote_number=f'QT-2024-{user.id}-{i:04d}',  # <-- UNIQUE PER USER
                customer_id=c.id, gst_percent=18, status=random.choice(q_statuses),
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
                    quotation_id=quote.id, product_id=p.id,
                    quantity=qty, unit_price=round(price), subtotal=line_total
                )
                db.session.add(qi)
            gst = subtotal * 0.18
            quote.subtotal = round(subtotal)
            quote.gst_amount = round(gst)
            quote.total_amount = round(subtotal + gst)

    db.session.commit()
    
    # Calculate RPI scores cleanly at the very end
    for c in Customer.query.all():
        update_customer_rpi(c.id)

    print("Seed data loaded successfully with isolated user data!")
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True, port=5000)