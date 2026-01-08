# Simple Invoice App

Aplicación web mínima para crear facturas en PDF y enviarlas por email desde un único contenedor Docker.

## Estructura

- `app.py`: aplicación Flask + lógica de facturas, SQLite, PDF y envío SMTP.
- `templates/`: plantillas HTML (`base.html`, `invoice_form.html`, `invoice_pdf.html`, `login.html`).
- `static/styles.css`: estilos sencillos y responsive.
- `database/`: carpeta donde se crea automáticamente `invoices.db`.
- `generated_invoices/`: PDFs generados.
- `requirements.txt`: dependencias Python.
- `Dockerfile`: imagen única para todo.
- `create_user.py`: script para crear usuarios en la base de datos.

## Variables de entorno

- `APP_SECRET_KEY` (opcional, por defecto `change-me`)
- `VAT_RATE` (opcional, por defecto `0.21`)
- `SMTP_HOST`
- `SMTP_PORT` (por defecto `587`)
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM` (si no se indica, usa `SMTP_USER`)
- `PORT` (por defecto `5000`)

## Ejecutar con Docker

```bash
docker build -t invoice-app .

docker run -d \
  -p 5000:5000 \
  -e SMTP_HOST="smtp.example.com" \
  -e SMTP_PORT="587" \
  -e SMTP_USER="usuario@example.com" \
  -e SMTP_PASSWORD="tu_password" \
  -e SMTP_FROM="facturas@example.com" \
  -e VAT_RATE="0.21" \
  --name invoice-app \
  invoice-app
```

Luego abre `http://localhost:5000` en el navegador.

## Autenticación

La aplicación requiere iniciar sesión para acceder. Todas las rutas están protegidas.

### Crear un usuario

Antes de usar la aplicación, debes crear al menos un usuario:

```bash
python create_user.py <username> <password>
```

Ejemplo:
```bash
python create_user.py admin mi_password_seguro
```

**Nota:** Asegúrate de que la base de datos ya existe (ejecuta la aplicación una vez antes de crear usuarios).

### Iniciar sesión

Una vez creado el usuario, accede a `http://localhost:5000` y serás redirigido al formulario de login. Introduce tu usuario y contraseña para acceder a la aplicación.


