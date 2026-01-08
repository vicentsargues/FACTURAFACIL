import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from io import BytesIO
import smtplib
from email.message import EmailMessage

from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "invoices.db"
PDF_DIR = BASE_DIR / "generated_invoices"
CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_CONFIG = {
    "company": {
        "name": "CRISTIAN MONTERDE CASTILLO",
        "tax_id": "73.660.137-S",
        "address": "C/Protectora, 17",
        "city": "46320 SINARCAS",
        "province": "(VALENCIA)",
        "logo_path": "logo.jpg",
    }
}


def create_app():
    # Create Flask app
    app = Flask(__name__)
    app.secret_key = os.environ.get("APP_SECRET_KEY", "change-me-in-production-use-strong-random-key")  # Simple secret for flashes

    # Ensure folders exist
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")

    init_db()

    # Load company info (issuer) from config file
    app.config["COMPANY_INFO"] = load_company_info()

    # Decorator to require login
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user_id"):
                flash("Debes iniciar sesión para acceder a esta página.", "error")
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated_function

    @app.route("/")
    def index():
        # Redirect to login if not authenticated, otherwise to new invoice form
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return redirect(url_for("new_invoice"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("user_id"):
            return redirect(url_for("new_invoice"))
        
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            
            if not username or not password:
                flash("Usuario y contraseña son obligatorios.", "error")
                return render_template("login.html")
            
            conn = get_db()
            user = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username,)
            ).fetchone()
            
            if not user:
                conn.close()
                flash("Usuario o contraseña incorrectos.", "error")
                return render_template("login.html")
            
            # Verificar contraseña
            password_valid = check_password_hash(user["password_hash"], password)
            conn.close()
            
            if password_valid:
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                flash("Sesión iniciada correctamente.", "success")
                return redirect(url_for("new_invoice"))
            else:
                flash("Usuario o contraseña incorrectos.", "error")
                return render_template("login.html")
        
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        session.clear()
        flash("Sesión cerrada correctamente.", "success")
        return redirect(url_for("login"))

    @app.route("/invoice/new", methods=["GET", "POST"])
    @login_required
    def new_invoice():
        conn = get_db()
        clients = conn.execute(
            "SELECT id, name, email, address, city, province, tax_id FROM clients ORDER BY name"
        ).fetchall()
        clients_data = [
            {
                "id": c["id"],
                "name": c["name"],
                "email": c["email"],
                "address": c["address"] or "",
                "city": c["city"] or "",
                "province": c["province"] or "",
                "tax_id": c["tax_id"] or "",
            }
            for c in clients
        ]

        if request.method == "POST":
            client_name = request.form.get("client_name", "").strip()
            client_email = request.form.get("client_email", "").strip()
            client_address = request.form.get("client_address", "").strip()
            client_city = request.form.get("client_city", "").strip()
            client_province = request.form.get("client_province", "").strip()
            client_tax_id = request.form.get("client_tax_id", "").strip()

            descriptions = request.form.getlist("item_description")
            prices_raw = request.form.getlist("item_price")

            # Basic validations (simple, not exhaustive)
            if not client_name or not client_email:
                flash("Nombre y email del cliente son obligatorios.", "error")
                return render_template("invoice_form.html", clients=clients)

            items = []
            for desc, price_str in zip(descriptions, prices_raw):
                desc = desc.strip()
                price_str = price_str.strip()
                if not desc and not price_str:
                    continue
                if not price_str:
                    continue
                try:
                    price = float(price_str.replace(",", "."))
                except ValueError:
                    flash("Precio inválido en una de las líneas.", "error")
                    return render_template("invoice_form.html", clients=clients)
                if price < 0:
                    flash("El precio no puede ser negativo.", "error")
                    return render_template("invoice_form.html", clients=clients)
                items.append({"description": desc or "-", "price": price})

            if not items:
                flash("Debe añadir al menos una línea de concepto.", "error")
                return render_template("invoice_form.html", clients=clients)

            vat_rate = float(os.environ.get("VAT_RATE", "0.21"))
            subtotal = sum(item["price"] for item in items)
            vat_amount = round(subtotal * vat_rate, 2)
            total = round(subtotal + vat_amount, 2)

            # Store in DB
            cur = conn.cursor()
            client_id = get_or_create_client(
                cur,
                client_name,
                client_email,
                client_address,
                client_city,
                client_province,
                client_tax_id,
            )


            # 👇 FECHA FACTURA (OPCIONAL)
            invoice_date_raw = request.form.get("invoice_date")
            if invoice_date_raw:
                invoice_date = invoice_date_raw
            else:
                invoice_date = datetime.now().strftime("%Y-%m-%d")


            cur.execute(
                """
                INSERT INTO invoices (client_id, date, subtotal, vat, total)
                VALUES (?, ?, ?, ?, ?)
                """,
                (client_id, invoice_date, subtotal, vat_amount, total),
            )
            invoice_id = cur.lastrowid

            for item in items:
                cur.execute(
                    """
                    INSERT INTO invoice_items (invoice_id, description, price)
                    VALUES (?, ?, ?)
                    """,
                    (invoice_id, item["description"], item["price"]),
                )

            conn.commit()

            # Load full invoice for PDF and email
            invoice_data = get_invoice(conn, invoice_id)

            # Generate PDF and save it
            pdf_path = PDF_DIR / f"invoice_{invoice_id}.pdf"
            generate_invoice_pdf(invoice_data, pdf_path, app.config["COMPANY_INFO"])

            # Send email with PDF attached
            try:
                send_invoice_email(invoice_data, pdf_path)
                flash("Factura creada y enviada por email correctamente.", "success")
            except Exception as e:
                # Simple error handling
                flash(f"Factura creada, pero hubo un error enviando el email: {e}", "error")

            return redirect(url_for("view_invoice", invoice_id=invoice_id))

        return render_template("invoice_form.html", clients=clients, clients_data=clients_data)

    @app.route("/invoice/<int:invoice_id>")
    @login_required
    def view_invoice(invoice_id):
        conn = get_db()
        invoice = get_invoice(conn, invoice_id)
        if not invoice:
            return "Factura no encontrada", 404
        return render_template(
            "invoice_pdf.html",
            invoice=invoice,
            company=app.config["COMPANY_INFO"],
        )

    @app.route("/invoice/<int:invoice_id>/pdf")
    @login_required
    def download_invoice_pdf(invoice_id):
        pdf_path = PDF_DIR / f"invoice_{invoice_id}.pdf"
        if not pdf_path.exists():
            # Regenerate if missing
            conn = get_db()
            invoice = get_invoice(conn, invoice_id)
            if not invoice:
                return "Factura no encontrada", 404
            generate_invoice_pdf(invoice, pdf_path, app.config["COMPANY_INFO"])

        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"factura_{invoice_id}.pdf",
        )

    return app


def get_db():
    # Open SQLite connection
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    # Initialize DB schema if not exists
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE
        )
        """
    )

    # Add missing columns to clients (idempotent)
    ensure_column(cur, "clients", "address", "TEXT")
    ensure_column(cur, "clients", "city", "TEXT")
    ensure_column(cur, "clients", "province", "TEXT")
    ensure_column(cur, "clients", "tax_id", "TEXT")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            subtotal REAL NOT NULL,
            vat REAL NOT NULL,
            total REAL NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        )
        """
    )

    # Create users table for authentication
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Create default admin user if no users exist
    cur.execute("SELECT COUNT(*) as count FROM users")
    user_count = cur.fetchone()[0]
    if user_count == 0:
        from werkzeug.security import generate_password_hash
        default_password = "adminVSB2001."  # Cambiar en producción
        password_hash = generate_password_hash(default_password)
        try:
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("admin", password_hash)
            )
            print("[INFO] Usuario por defecto creado: admin / adminVSB2001.")
            print("[ADVERTENCIA] Cambia la contraseña por defecto en producción!")
        except sqlite3.IntegrityError:
            pass  # User already exists

    conn.commit()
    conn.close()


def ensure_column(cur, table: str, column: str, col_type: str):
    """Add column if missing (simple, idempotent)."""
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def get_or_create_client(cur, name, email, address, city, province, tax_id):
    # Get existing client by email or create a new one
    cur.execute("SELECT id FROM clients WHERE email = ?", (email,))
    row = cur.fetchone()
    if row:
        # Update name in case it changed
        cur.execute(
            """
            UPDATE clients
            SET name = ?, address = ?, city = ?, province = ?, tax_id = ?
            WHERE id = ?
            """,
            (name, address, city, province, tax_id, row[0]),
        )
        return row[0]
    cur.execute(
        """
        INSERT INTO clients (name, email, address, city, province, tax_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, email, address, city, province, tax_id),
    )
    return cur.lastrowid


def get_invoice(conn, invoice_id):
    # Load invoice with client and items
    cur = conn.cursor()
    cur.execute(
        """
        SELECT i.id, i.date, i.subtotal, i.vat, i.total,
               c.name AS client_name, c.email AS client_email,
               c.address AS client_address, c.city AS client_city,
               c.province AS client_province, c.tax_id AS client_tax_id
        FROM invoices i
        JOIN clients c ON i.client_id = c.id
        WHERE i.id = ?
        """,
        (invoice_id,),
    )
    invoice_row = cur.fetchone()
    if not invoice_row:
        return None

    cur.execute(
        """
        SELECT description, price
        FROM invoice_items
        WHERE invoice_id = ?
        """,
        (invoice_id,),
    )
    items = cur.fetchall()

    return {
        "id": invoice_row["id"],
        "date": invoice_row["date"],
        "subtotal": invoice_row["subtotal"],
        "vat": invoice_row["vat"],
        "total": invoice_row["total"],
        "client_name": invoice_row["client_name"],
        "client_email": invoice_row["client_email"],
        "client_address": invoice_row["client_address"],
        "client_city": invoice_row["client_city"],
        "client_province": invoice_row["client_province"],
        "client_tax_id": invoice_row["client_tax_id"],
        "items": [{"description": it["description"], "price": it["price"]} for it in items],
    }


def generate_invoice_pdf(invoice, pdf_path: Path, company_info: dict):
    # Generar PDF de factura usando ReportLab
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Márgenes y configuración
    margin_left = 20 * mm
    margin_right = width - 20 * mm
    margin_top = height - 20 * mm
    y = margin_top

    # 1. LOGO MÁS GRANDE (ajustado a 60mm de ancho)
    logo_path = company_info.get("logo_path")
    if logo_path:
        logo_file = (BASE_DIR / logo_path).resolve()
        if logo_file.exists():
            try:
                c.drawImage(
                    str(logo_file),
                    margin_right - 65 * mm, # Posición X
                    y - 35 * mm,            # Posición Y
                    width=60 * mm,          # Antes era 45mm
                    height=35 * mm,         # Antes era 25mm
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

    # 2. CABECERA: TÍTULO, NÚMERO, FECHA Y CÓDIGO
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin_left, y, "FACTURA")
    
    y -= 25
    c.setFont("Helvetica", 10)
    invoice_num = f"{invoice['id']:05d}"
    invoice_year = invoice['date'].split('-')[0] # Extrae el año de YYYY-MM-DD
    
    c.drawString(margin_left, y, f"Número: {invoice_num}")
    y -= 15
    c.drawString(margin_left, y, f"Fecha: {invoice['date']}")
    y -= 15
    # Nuevo campo Código: Numero/Año
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y, f"Código: {invoice_num}/{invoice_year}")

    # 3. INFO EMPRESA (Emisor)
    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_left, y, company_info.get("name", ""))
    y -= 15
    c.setFont("Helvetica", 10)
    if company_info.get("tax_id"):
        c.drawString(margin_left, y, f"NIF: {company_info['tax_id']}")
        y -= 15
    if company_info.get("address"):
        c.drawString(margin_left, y, company_info["address"])
        y -= 15
    
    city_line = " ".join(filter(None, [company_info.get("city", ""), company_info.get("province", "")])).strip()
    if city_line:
        c.drawString(margin_left, y, city_line)
        y -= 20 # Espacio antes del bloque de cliente

    # 4. INFO CLIENTE (Ahora justo debajo de la empresa)
    c.setDash(1, 2) # Línea punteada sutil para separar secciones
    c.line(margin_left, y + 5, margin_left + 50*mm, y + 5)
    c.setDash() # Volver a línea sólida
    
    y -= 10
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left, y, "DATOS DEL CLIENTE:")
    y -= 15
    c.setFont("Helvetica", 10)
    c.drawString(margin_left, y, invoice.get("client_name", ""))
    y -= 15
    if invoice.get("client_tax_id"):
        c.drawString(margin_left, y, f"CIF/NIF: {invoice['client_tax_id']}")
        y -= 15
    if invoice.get("client_address"):
        c.drawString(margin_left, y, invoice["client_address"])
        y -= 15
    
    city_client = " ".join(filter(None, [invoice.get("client_city", ""), invoice.get("client_province", "")])).strip()
    if city_client:
        c.drawString(margin_left, y, city_client)
        y -= 15

    # 5. TABLA DE CONCEPTOS
    table_top = y - 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, table_top, "Descripción")
    c.drawRightString(margin_right, table_top, "Importe")
    c.line(margin_left, table_top - 5, margin_right, table_top - 5)

    y = table_top - 20
    c.setFont("Helvetica", 10)
    for item in invoice["items"]:
        if y < 60 * mm: # Control de salto de página
            c.showPage()
            y = margin_top - 20
            c.setFont("Helvetica", 10)
        
        desc = item["description"]
        c.drawString(margin_left, y, desc[:70] + ("..." if len(desc) > 70 else ""))
        c.drawRightString(margin_right, y, f"{item['price']:.2f} €")
        y -= 15

    # 6. TOTALES
    y -= 10
    c.line(margin_left, y, margin_right, y)
    y -= 20
    
    c.setFont("Helvetica", 10)
    c.drawRightString(margin_right, y, f"Subtotal: {invoice['subtotal']:.2f} €")
    y -= 15
    c.drawRightString(margin_right, y, f"IVA (21%): {invoice['vat']:.2f} €")
    y -= 15
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(margin_right, y, f"TOTAL A PAGAR: {invoice['total']:.2f} €")

    # 7. PIE DE PÁGINA CON CUENTA BANCARIA (Hardcodeado)
    y_footer = 30 * mm
    c.line(margin_left, y_footer, margin_right, y_footer)
    y_footer -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y_footer, "Nº cta. para realizar la transferencia:")
    y_footer -= 15
    c.setFont("Courier", 11) # Fuente monoespaciada para el IBAN queda mejor
    c.drawString(margin_left, y_footer, "ES55 3058 7081 1428 2060 0662")

    c.showPage()
    c.save()

    # Guardar en archivo
    pdf_path.write_bytes(buffer.getvalue())

def load_company_info():
    """Load company info from config.json file."""
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")
        return DEFAULT_CONFIG["company"]
    
    try:
        config_data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return config_data.get("company", DEFAULT_CONFIG["company"])
    except Exception:
        return DEFAULT_CONFIG["company"]


def send_invoice_email(invoice, pdf_path: Path):
    msg = EmailMessage()
    msg["Subject"] = f"Factura #{invoice['id']}"
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = invoice["client_email"]
    msg.set_content(f"Hola {invoice['client_name']},\n\nAdjuntamos la factura de sus servicios.\n\nUn saludo.")
    msg.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=f"factura_{invoice['id']}.pdf")

    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as server:
        server.starttls()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.send_message(msg)

if __name__ == "__main__":
    # CONFIGURACIÓN DE TU CUENTA GMAIL
    os.environ["SMTP_HOST"] = "smtp.gmail.com"
    os.environ["SMTP_PORT"] = "587"
    os.environ["SMTP_USER"] = "vicentsargues@gmail.com"
    os.environ["SMTP_PASSWORD"] = "bjreekvxnzgndfvv" # Tu contraseña de aplicación
    
    app = create_app()
    # Permite cambiar el puerto por variable de entorno (PORT), por defecto 5000.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)

