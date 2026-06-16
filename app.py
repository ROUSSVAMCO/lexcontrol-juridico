
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

app = Flask(__name__)
app.secret_key = "LEXCONTROL_CAMBIAR_CLAVE_2026"

DB_NAME = "lexcontrol.db"
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED_IMAGES = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_DOCS = {"pdf", "doc", "docx", "jpg", "jpeg", "png", "webp"}

# Enlaces jurídicos oficiales / públicos
SCJN_BUSCADOR = "https://bj.scjn.gob.mx/"
SCJN_TESIS = "https://sjf2.scjn.gob.mx/busqueda-principal-tesis"
BOLETIN_PJBC = "https://www.pjbc.gob.mx/boletin_judicial.aspx"
PJBC_PORTAL = "https://www.poder-judicial-bc.gob.mx/"
TEJA_BC = "https://tejabc.mx/"
TEJA_LISTAS = "https://tejabc.mx/buscarlistas"

def conectar():
    con = sqlite3.connect(DB_NAME)
    con.row_factory = sqlite3.Row
    return con

def permitido(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed

def crear_tablas():
    with conectar() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                nombre_sistema TEXT,
                subtitulo TEXT,
                portada TEXT,
                logo TEXT,
                color_principal TEXT,
                color_secundario TEXT,
                color_acento TEXT
            )
        """)
        con.execute("""
            INSERT OR IGNORE INTO configuracion
            (id, nombre_sistema, subtitulo, portada, logo, color_principal, color_secundario, color_acento)
            VALUES
            (1, 'LEXCONTROL Jurídico', 'Control profesional de expedientes, promociones y vencimientos', '', '', '#0f172a', '#1e293b', '#b38b2e')
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                usuario TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL DEFAULT 'Usuario',
                foto TEXT,
                activo INTEGER NOT NULL DEFAULT 1,
                creado_en TEXT
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS expedientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                propietario_id INTEGER NOT NULL,
                numero TEXT NOT NULL,
                tipo TEXT NOT NULL,
                autoridad TEXT,
                actor TEXT,
                demandado TEXT,
                estado TEXT NOT NULL,
                responsable TEXT,
                fecha_inicio TEXT,
                observaciones TEXT,
                creado_en TEXT,
                FOREIGN KEY(propietario_id) REFERENCES usuarios(id)
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS expedientes_compartidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expediente_id INTEGER NOT NULL,
                usuario_id INTEGER NOT NULL,
                permiso TEXT NOT NULL DEFAULT 'Lectura',
                creado_en TEXT,
                UNIQUE(expediente_id, usuario_id),
                FOREIGN KEY(expediente_id) REFERENCES expedientes(id),
                FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expediente_id INTEGER NOT NULL,
                usuario_id INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                fecha TEXT,
                estatus TEXT,
                proxima_accion TEXT,
                fecha_limite TEXT,
                observaciones TEXT,
                archivo TEXT,
                creado_en TEXT,
                FOREIGN KEY(expediente_id) REFERENCES expedientes(id),
                FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
            )
        """)

        total = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if total == 0:
            con.execute("""
                INSERT INTO usuarios (nombre, usuario, password_hash, rol, foto, activo, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                "Administrador General",
                "admin",
                generate_password_hash("Admin123*"),
                "Administrador",
                "",
                1,
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
        con.commit()

crear_tablas()

def obtener_config():
    with conectar() as con:
        return con.execute("SELECT * FROM configuracion WHERE id=1").fetchone()

def usuario_actual():
    if "usuario_id" not in session:
        return None
    with conectar() as con:
        return con.execute("SELECT * FROM usuarios WHERE id=? AND activo=1", (session["usuario_id"],)).fetchone()

def requiere_login():
    return "usuario_id" in session

def es_admin():
    u = usuario_actual()
    return bool(u and u["rol"] == "Administrador")

def permiso_expediente(expediente_id):
    u = usuario_actual()
    if not u:
        return None
    with conectar() as con:
        exp = con.execute("SELECT * FROM expedientes WHERE id=?", (expediente_id,)).fetchone()
        if not exp:
            return None
        if u["rol"] == "Administrador" or exp["propietario_id"] == u["id"]:
            return "Edición"
        comp = con.execute("""
            SELECT permiso FROM expedientes_compartidos
            WHERE expediente_id=? AND usuario_id=?
        """, (expediente_id, u["id"])).fetchone()
        return comp["permiso"] if comp else None

@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

BASE = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>{{config.nombre_sistema}}</title>
<style>
:root{
    --principal: {{config.color_principal or '#0f172a'}};
    --secundario: {{config.color_secundario or '#1e293b'}};
    --acento: {{config.color_acento or '#b38b2e'}};
    --gris:#f3f4f6;
}
body{margin:0;font-family:Arial, sans-serif;background:var(--gris);color:#1f2937;}
.top{background:var(--principal);color:white;padding:8px 28px;display:flex;justify-content:space-between;font-size:14px;}
.hero{
    min-height:220px;
    background:
    linear-gradient(rgba(15,23,42,.72),rgba(15,23,42,.72)),
    {% if config.portada %}url('/uploads/{{config.portada}}'){% else %}linear-gradient(135deg,var(--principal),var(--secundario)){% endif %};
    background-size:cover;background-position:center;color:white;display:flex;align-items:end;
    padding:28px 36px;box-sizing:border-box;border-bottom:6px solid var(--acento);
}
.brand{display:flex;align-items:center;gap:18px;}
.logo{width:95px;height:95px;border-radius:50%;border:4px solid white;object-fit:cover;background:white;}
.brand h1{margin:0;font-size:34px;letter-spacing:.5px;}
.brand p{margin:6px 0 0;opacity:.92;}
nav{background:var(--secundario);padding:12px 30px;}
nav a{color:white;text-decoration:none;margin-right:16px;font-weight:bold;font-size:14px;}
nav a:hover{color:#fde68a;}
main{padding:25px 30px;}
.card{background:white;padding:22px;border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(15,23,42,.1);border-top:3px solid var(--acento);}
input,select,textarea{width:100%;padding:11px;margin:6px 0 13px;border:1px solid #cbd5e1;border-radius:7px;box-sizing:border-box;font-size:14px;}
label{font-weight:bold;font-size:14px;}
button,.btn{background:var(--principal);color:white;border:0;padding:10px 16px;border-radius:7px;text-decoration:none;display:inline-block;font-weight:bold;cursor:pointer;}
.btn2{background:#475569}.btnGold{background:#9a6f14}.btnGreen{background:#166534}.btnRed{background:#991b1b}
table{width:100%;border-collapse:collapse;background:white;} th,td{padding:10px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top;} th{background:#e2e8f0;color:#0f172a;}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:15px}
.stat{background:white;padding:20px;border-radius:12px;text-align:center;box-shadow:0 2px 12px rgba(15,23,42,.1);border-bottom:4px solid var(--acento);}
.stat h2{font-size:34px;margin:0;color:var(--principal);}
.tag{padding:5px 9px;border-radius:999px;font-size:12px;font-weight:bold;display:inline-block;}
.En-trámite,.Pendiente,.Lectura{background:#fef3c7}.Urgente,.Vencido{background:#fecaca}.Concluido,.Acordado,.Edición{background:#bbf7d0}.Presentado{background:#bfdbfe}
.flash{background:#dcfce7;border-left:5px solid #166534;padding:10px;border-radius:7px;margin-bottom:12px;}
.login{max-width:430px;margin:35px auto}.preview{max-width:260px;max-height:150px;border:1px solid #ddd;border-radius:8px;display:block;margin:8px 0 15px;}
.small{font-size:13px;color:#64748b}
@media(max-width:900px){.grid,.grid2{grid-template-columns:1fr}nav a{display:inline-block;margin-bottom:8px}table{font-size:13px}}
</style>
</head>
<body>
<div class="top">
    <div>Sistema jurídico privado</div>
    <div>
    {% if usuario %}
        {{usuario.nombre}} | {{usuario.rol}} | <a href="/logout" style="color:white">Salir</a>
    {% else %}
        Acceso restringido
    {% endif %}
    </div>
</div>
<section class="hero">
    <div class="brand">
        {% if config.logo %}<img class="logo" src="/uploads/{{config.logo}}">{% else %}<div class="logo"></div>{% endif %}
        <div><h1>{{config.nombre_sistema}}</h1><p>{{config.subtitulo}}</p></div>
    </div>
</section>
{% if usuario %}
<nav>
    <a href="/">Inicio</a>
    <a href="/expedientes">Mis expedientes</a>
    <a href="/compartidos">Compartidos conmigo</a>
    <a href="/nuevo">Nuevo expediente</a>
    <a href="/vencimientos">Vencimientos</a>
    <a href="/jurisprudencia">Jurisprudencia / Enlaces</a>
    {% if usuario.rol == 'Administrador' %}
        <a href="/usuarios">Usuarios</a>
        <a href="/configuracion">Visual / Imágenes</a>
    {% endif %}
</nav>
{% endif %}
<main>
{% with messages=get_flashed_messages() %}
{% for message in messages %}<div class="flash">{{message}}</div>{% endfor %}
{% endwith %}
{{contenido|safe}}
</main>
</body>
</html>
"""

def render(contenido, **kwargs):
    return render_template_string(BASE, contenido=render_template_string(contenido, **kwargs), config=obtener_config(), usuario=usuario_actual())

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = request.form["usuario"].strip()
        pwd = request.form["password"]
        with conectar() as con:
            u = con.execute("SELECT * FROM usuarios WHERE usuario=? AND activo=1", (user,)).fetchone()
        if u and check_password_hash(u["password_hash"], pwd):
            session["usuario_id"] = u["id"]
            flash("Acceso correcto.")
            return redirect(url_for("inicio"))
        flash("Usuario o contraseña incorrectos.")
    contenido = """
    <div class="card login">
        <h2>Iniciar sesión</h2>
        <form method="post">
            <label>Usuario</label><input name="usuario" required>
            <label>Contraseña</label><input type="password" name="password" required>
            <button>Entrar</button>
        </form>
        <p class="small"><b>Administrador inicial:</b> usuario <b>admin</b> / contraseña <b>Admin123*</b></p>
    </div>
    """
    return render(contenido)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def inicio():
    if not requiere_login(): return redirect(url_for("login"))
    u = usuario_actual()
    with conectar() as con:
        propios = con.execute("SELECT COUNT(*) FROM expedientes WHERE propietario_id=?", (u["id"],)).fetchone()[0]
        compartidos = con.execute("SELECT COUNT(*) FROM expedientes_compartidos WHERE usuario_id=?", (u["id"],)).fetchone()[0]
        if u["rol"] == "Administrador":
            total = con.execute("SELECT COUNT(*) FROM expedientes").fetchone()[0]
            urgentes = con.execute("SELECT COUNT(*) FROM expedientes WHERE estado='Urgente'").fetchone()[0]
            recientes = con.execute("""SELECT e.*, us.nombre propietario FROM expedientes e JOIN usuarios us ON us.id=e.propietario_id ORDER BY e.id DESC LIMIT 8""").fetchall()
        else:
            total = propios + compartidos
            urgentes = con.execute("SELECT COUNT(*) FROM expedientes WHERE propietario_id=? AND estado='Urgente'", (u["id"],)).fetchone()[0]
            recientes = con.execute("""SELECT e.*, us.nombre propietario FROM expedientes e JOIN usuarios us ON us.id=e.propietario_id WHERE e.propietario_id=? ORDER BY e.id DESC LIMIT 8""", (u["id"],)).fetchall()
    contenido = """
    <div class="grid">
        <div class="stat"><h2>{{total}}</h2><p>Expedientes visibles</p></div>
        <div class="stat"><h2>{{propios}}</h2><p>Mis expedientes</p></div>
        <div class="stat"><h2>{{compartidos}}</h2><p>Compartidos conmigo</p></div>
        <div class="stat"><h2>{{urgentes}}</h2><p>Urgentes</p></div>
    </div><br>
    <div class="card">
        <h2>Accesos jurídicos rápidos</h2>
        <a class="btn btnGold" target="_blank" href="{{SCJN_BUSCADOR}}">Buscador Jurídico SCJN</a>
        <a class="btn btnGold" target="_blank" href="{{SCJN_TESIS}}">Semanario Judicial / Tesis</a>
        <a class="btn btn2" target="_blank" href="{{BOLETIN_PJBC}}">Boletín Judicial BC</a>
        <a class="btn btn2" target="_blank" href="{{PJBC_PORTAL}}">Poder Judicial BC</a>
        <a class="btn btn2" target="_blank" href="{{TEJA_BC}}">TEJA BC</a>
        <a class="btn btn2" target="_blank" href="{{TEJA_LISTAS}}">Listas TEJA</a>
    </div>
    <div class="card">
        <h2>Últimos expedientes</h2>
        <table><tr><th>Expediente</th><th>Tipo</th><th>Autoridad</th><th>Estado</th><th>Propietario</th><th>Acción</th></tr>
        {% for e in recientes %}
        <tr><td>{{e.numero}}</td><td>{{e.tipo}}</td><td>{{e.autoridad}}</td><td><span class="tag {{e.estado.replace(' ','-')}}">{{e.estado}}</span></td><td>{{e.propietario}}</td><td><a class="btn btn2" href="/expediente/{{e.id}}">Abrir</a></td></tr>
        {% endfor %}
        </table>
    </div>
    """
    return render(contenido, total=total, propios=propios, compartidos=compartidos, urgentes=urgentes, recientes=recientes, SCJN_BUSCADOR=SCJN_BUSCADOR, SCJN_TESIS=SCJN_TESIS, BOLETIN_PJBC=BOLETIN_PJBC, PJBC_PORTAL=PJBC_PORTAL, TEJA_BC=TEJA_BC, TEJA_LISTAS=TEJA_LISTAS)

@app.route("/usuarios", methods=["GET","POST"])
def usuarios():
    if not requiere_login(): return redirect(url_for("login"))
    if not es_admin():
        flash("Solo el administrador puede acceder.")
        return redirect(url_for("inicio"))
    if request.method == "POST":
        with conectar() as con:
            total = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
            if total >= 15:
                flash("Límite alcanzado: solo se permiten 15 usuarios.")
                return redirect(url_for("usuarios"))
            foto_nombre = ""
            foto = request.files.get("foto")
            if foto and foto.filename:
                if not permitido(foto.filename, ALLOWED_IMAGES):
                    flash("La foto debe ser imagen.")
                    return redirect(url_for("usuarios"))
                foto_nombre = "usuario_" + datetime.now().strftime("%Y%m%d%H%M%S_") + secure_filename(foto.filename)
                foto.save(UPLOAD_FOLDER / foto_nombre)
            try:
                con.execute("""INSERT INTO usuarios(nombre,usuario,password_hash,rol,foto,activo,creado_en) VALUES(?,?,?,?,?,1,?)""",
                    (request.form["nombre"], request.form["usuario"], generate_password_hash(request.form["password"]), request.form["rol"], foto_nombre, datetime.now().strftime("%Y-%m-%d %H:%M")))
                con.commit()
                flash("Usuario creado correctamente.")
            except sqlite3.IntegrityError:
                flash("Ese usuario ya existe.")
        return redirect(url_for("usuarios"))
    with conectar() as con:
        datos = con.execute("SELECT * FROM usuarios ORDER BY id").fetchall()
        total = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    contenido = """
    <div class="grid2">
    <div class="card">
        <h2>Crear usuario</h2>
        <p>Registrados: <b>{{total}}</b> de <b>15</b>.</p>
        <form method="post" enctype="multipart/form-data">
            <label>Nombre completo</label><input name="nombre" required>
            <label>Usuario</label><input name="usuario" required>
            <label>Contraseña</label><input type="password" name="password" required>
            <label>Rol</label><select name="rol"><option>Usuario</option><option>Administrador</option></select>
            <label>Foto de perfil</label><input type="file" name="foto" accept="image/*">
            <button>Crear usuario</button>
        </form>
    </div>
    <div class="card">
        <h2>Usuarios</h2>
        <table><tr><th>ID</th><th>Nombre</th><th>Usuario</th><th>Rol</th></tr>
        {% for u in datos %}<tr><td>{{u.id}}</td><td>{{u.nombre}}</td><td>{{u.usuario}}</td><td>{{u.rol}}</td></tr>{% endfor %}
        </table>
    </div></div>
    """
    return render(contenido, datos=datos, total=total)

@app.route("/configuracion", methods=["GET","POST"])
def configuracion():
    if not requiere_login(): return redirect(url_for("login"))
    if not es_admin():
        flash("Solo el administrador puede modificar lo visual.")
        return redirect(url_for("inicio"))
    config = obtener_config()
    if request.method == "POST":
        portada_actual = config["portada"] or ""
        logo_actual = config["logo"] or ""
        portada = request.files.get("portada")
        logo = request.files.get("logo")
        if portada and portada.filename:
            if not permitido(portada.filename, ALLOWED_IMAGES):
                flash("La portada debe ser imagen.")
                return redirect(url_for("configuracion"))
            portada_actual = "portada_" + datetime.now().strftime("%Y%m%d%H%M%S_") + secure_filename(portada.filename)
            portada.save(UPLOAD_FOLDER / portada_actual)
        if logo and logo.filename:
            if not permitido(logo.filename, ALLOWED_IMAGES):
                flash("El logo debe ser imagen.")
                return redirect(url_for("configuracion"))
            logo_actual = "logo_" + datetime.now().strftime("%Y%m%d%H%M%S_") + secure_filename(logo.filename)
            logo.save(UPLOAD_FOLDER / logo_actual)
        with conectar() as con:
            con.execute("""UPDATE configuracion SET nombre_sistema=?, subtitulo=?, portada=?, logo=?, color_principal=?, color_secundario=?, color_acento=? WHERE id=1""",
                (request.form["nombre_sistema"], request.form["subtitulo"], portada_actual, logo_actual, request.form["color_principal"], request.form["color_secundario"], request.form["color_acento"]))
            con.commit()
        flash("Diseño actualizado correctamente.")
        return redirect(url_for("inicio"))
    contenido = """
    <div class="card">
        <h2>Modificar programa / visual / imágenes</h2>
        <form method="post" enctype="multipart/form-data">
            <label>Nombre del sistema</label><input name="nombre_sistema" value="{{config.nombre_sistema}}" required>
            <label>Subtítulo</label><input name="subtitulo" value="{{config.subtitulo}}">
            <label>Color principal</label><input type="color" name="color_principal" value="{{config.color_principal or '#0f172a'}}">
            <label>Color secundario</label><input type="color" name="color_secundario" value="{{config.color_secundario or '#1e293b'}}">
            <label>Color acento</label><input type="color" name="color_acento" value="{{config.color_acento or '#b38b2e'}}">
            <label>Imagen de portada</label>{% if config.portada %}<img class="preview" src="/uploads/{{config.portada}}">{% endif %}<input type="file" name="portada" accept="image/*">
            <label>Logo / foto de perfil del sistema</label>{% if config.logo %}<img class="preview" src="/uploads/{{config.logo}}">{% endif %}<input type="file" name="logo" accept="image/*">
            <button>Guardar diseño</button>
        </form>
    </div>
    """
    return render(contenido, config=config)

@app.route("/nuevo", methods=["GET","POST"])
def nuevo():
    if not requiere_login(): return redirect(url_for("login"))
    u = usuario_actual()
    if request.method == "POST":
        with conectar() as con:
            con.execute("""INSERT INTO expedientes(propietario_id,numero,tipo,autoridad,actor,demandado,estado,responsable,fecha_inicio,observaciones,creado_en) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (u["id"], request.form["numero"], request.form["tipo"], request.form["autoridad"], request.form["actor"], request.form["demandado"], request.form["estado"], request.form["responsable"], request.form["fecha_inicio"], request.form["observaciones"], datetime.now().strftime("%Y-%m-%d %H:%M")))
            con.commit()
        flash("Expediente guardado en tu espacio.")
        return redirect(url_for("expedientes"))
    contenido = """
    <div class="card"><h2>Nuevo expediente</h2>
    <form method="post">
        <label>Número de expediente</label><input name="numero" required>
        <label>Tipo</label><select name="tipo"><option>Laboral</option><option>Penal</option><option>Administrativo</option><option>Civil</option><option>Mercantil</option><option>Amparo</option><option>Familiar</option><option>Otro</option></select>
        <label>Autoridad / juzgado / tribunal</label><input name="autoridad">
        <label>Actor / denunciante</label><input name="actor">
        <label>Demandado / imputado</label><input name="demandado">
        <label>Estado</label><select name="estado"><option>En trámite</option><option>Pendiente</option><option>Urgente</option><option>Concluido</option></select>
        <label>Responsable</label><input name="responsable">
        <label>Fecha de inicio</label><input type="date" name="fecha_inicio">
        <label>Observaciones</label><textarea name="observaciones" rows="4"></textarea>
        <button>Guardar</button>
    </form></div>
    """
    return render(contenido)

@app.route("/expedientes")
def expedientes():
    if not requiere_login(): return redirect(url_for("login"))
    u=usuario_actual()
    q=request.args.get("q","").strip()
    like=f"%{q}%"
    with conectar() as con:
        if u["rol"]=="Administrador":
            datos=con.execute("""SELECT e.*,us.nombre propietario FROM expedientes e JOIN usuarios us ON us.id=e.propietario_id WHERE ?='' OR e.numero LIKE ? OR e.tipo LIKE ? OR e.autoridad LIKE ? OR e.actor LIKE ? OR e.demandado LIKE ? ORDER BY e.id DESC""",(q,like,like,like,like,like)).fetchall()
        else:
            datos=con.execute("""SELECT e.*,us.nombre propietario FROM expedientes e JOIN usuarios us ON us.id=e.propietario_id WHERE e.propietario_id=? AND (?='' OR e.numero LIKE ? OR e.tipo LIKE ? OR e.autoridad LIKE ? OR e.actor LIKE ? OR e.demandado LIKE ?) ORDER BY e.id DESC""",(u["id"],q,like,like,like,like,like)).fetchall()
    contenido = """
    <div class="card"><h2>Mis expedientes</h2>
    <form><input name="q" value="{{q}}" placeholder="Buscar expediente"><button>Buscar</button> <a class="btn btn2" href="/expedientes">Limpiar</a></form><br>
    <table><tr><th>Número</th><th>Tipo</th><th>Autoridad</th><th>Estado</th><th>Propietario</th><th>Acción</th></tr>
    {% for e in datos %}<tr><td>{{e.numero}}</td><td>{{e.tipo}}</td><td>{{e.autoridad}}</td><td><span class="tag {{e.estado.replace(' ','-')}}">{{e.estado}}</span></td><td>{{e.propietario}}</td><td><a class="btn btn2" href="/expediente/{{e.id}}">Abrir</a></td></tr>{% endfor %}
    </table></div>
    """
    return render(contenido, datos=datos, q=q)

@app.route("/compartidos")
def compartidos():
    if not requiere_login(): return redirect(url_for("login"))
    u=usuario_actual()
    with conectar() as con:
        datos=con.execute("""SELECT e.*,c.permiso,us.nombre propietario FROM expedientes_compartidos c JOIN expedientes e ON e.id=c.expediente_id JOIN usuarios us ON us.id=e.propietario_id WHERE c.usuario_id=? ORDER BY c.id DESC""",(u["id"],)).fetchall()
    contenido = """
    <div class="card"><h2>Compartidos conmigo</h2>
    <table><tr><th>Número</th><th>Tipo</th><th>Autoridad</th><th>Estado</th><th>Propietario</th><th>Permiso</th><th>Acción</th></tr>
    {% for e in datos %}<tr><td>{{e.numero}}</td><td>{{e.tipo}}</td><td>{{e.autoridad}}</td><td><span class="tag {{e.estado.replace(' ','-')}}">{{e.estado}}</span></td><td>{{e.propietario}}</td><td><span class="tag {{e.permiso}}">{{e.permiso}}</span></td><td><a class="btn btn2" href="/expediente/{{e.id}}">Abrir</a></td></tr>{% endfor %}
    </table></div>
    """
    return render(contenido, datos=datos)

@app.route("/expediente/<int:id>")
def expediente(id):
    if not requiere_login(): return redirect(url_for("login"))
    permiso=permiso_expediente(id)
    if not permiso:
        flash("No tienes acceso a ese expediente.")
        return redirect(url_for("inicio"))
    with conectar() as con:
        e=con.execute("""SELECT e.*,us.nombre propietario FROM expedientes e JOIN usuarios us ON us.id=e.propietario_id WHERE e.id=?""",(id,)).fetchone()
        movs=con.execute("""SELECT m.*,us.nombre autor FROM movimientos m JOIN usuarios us ON us.id=m.usuario_id WHERE m.expediente_id=? ORDER BY m.id DESC""",(id,)).fetchall()
        compart=con.execute("""SELECT c.*,us.nombre,us.usuario FROM expedientes_compartidos c JOIN usuarios us ON us.id=c.usuario_id WHERE c.expediente_id=?""",(id,)).fetchall()
    contenido = """
    <div class="card">
    <h2>Expediente {{e.numero}}</h2>
    <p><b>Propietario:</b> {{e.propietario}}</p><p><b>Tipo:</b> {{e.tipo}}</p><p><b>Autoridad:</b> {{e.autoridad}}</p><p><b>Actor:</b> {{e.actor}}</p><p><b>Demandado:</b> {{e.demandado}}</p><p><b>Estado:</b> <span class="tag {{e.estado.replace(' ','-')}}">{{e.estado}}</span></p><p><b>Observaciones:</b> {{e.observaciones}}</p>
    {% if permiso == 'Edición' %}<a class="btn" href="/movimiento/{{e.id}}">Agregar promoción</a> <a class="btn btnGold" href="/compartir/{{e.id}}">Compartir</a>{% endif %}
    </div>
    <div class="grid2"><div class="card"><h2>Historial</h2>
    <table><tr><th>Título</th><th>Fecha</th><th>Estatus</th><th>Límite</th><th>Archivo</th><th>Autor</th></tr>
    {% for m in movs %}<tr><td>{{m.titulo}}<br><small>{{m.observaciones}}</small></td><td>{{m.fecha}}</td><td><span class="tag {{m.estatus.replace(' ','-')}}">{{m.estatus}}</span></td><td>{{m.fecha_limite}}</td><td>{% if m.archivo %}<a target="_blank" href="/uploads/{{m.archivo}}">Ver</a>{% endif %}</td><td>{{m.autor}}</td></tr>{% endfor %}
    </table></div><div class="card"><h2>Compartido con</h2><table><tr><th>Nombre</th><th>Usuario</th><th>Permiso</th></tr>{% for c in compart %}<tr><td>{{c.nombre}}</td><td>{{c.usuario}}</td><td><span class="tag {{c.permiso}}">{{c.permiso}}</span></td></tr>{% endfor %}</table></div></div>
    """
    return render(contenido, e=e, movs=movs, compart=compart, permiso=permiso)

@app.route("/compartir/<int:expediente_id>", methods=["GET","POST"])
def compartir(expediente_id):
    if not requiere_login(): return redirect(url_for("login"))
    if permiso_expediente(expediente_id)!="Edición":
        flash("No tienes permiso para compartir.")
        return redirect(url_for("expediente", id=expediente_id))
    u=usuario_actual()
    if request.method=="POST":
        with conectar() as con:
            con.execute("""INSERT OR REPLACE INTO expedientes_compartidos(expediente_id,usuario_id,permiso,creado_en) VALUES(?,?,?,?)""",(expediente_id,request.form["usuario_id"],request.form["permiso"],datetime.now().strftime("%Y-%m-%d %H:%M")))
            con.commit()
        flash("Expediente compartido.")
        return redirect(url_for("expediente", id=expediente_id))
    with conectar() as con:
        e=con.execute("SELECT * FROM expedientes WHERE id=?",(expediente_id,)).fetchone()
        usuarios=con.execute("SELECT * FROM usuarios WHERE activo=1 AND id!=? ORDER BY nombre",(u["id"],)).fetchall()
    contenido = """
    <div class="card"><h2>Compartir expediente {{e.numero}}</h2>
    <form method="post"><label>Usuario</label><select name="usuario_id">{% for us in usuarios %}<option value="{{us.id}}">{{us.nombre}} - {{us.usuario}}</option>{% endfor %}</select>
    <label>Permiso</label><select name="permiso"><option>Lectura</option><option>Edición</option></select><button>Compartir</button></form></div>
    """
    return render(contenido, e=e, usuarios=usuarios)

@app.route("/movimiento/<int:expediente_id>", methods=["GET","POST"])
def movimiento(expediente_id):
    if not requiere_login(): return redirect(url_for("login"))
    if permiso_expediente(expediente_id)!="Edición":
        flash("No tienes permiso de edición.")
        return redirect(url_for("expediente", id=expediente_id))
    u=usuario_actual()
    if request.method=="POST":
        archivo_nombre=""
        archivo=request.files.get("archivo")
        if archivo and archivo.filename:
            if not permitido(archivo.filename, ALLOWED_DOCS):
                flash("Archivo no permitido.")
                return redirect(url_for("movimiento", expediente_id=expediente_id))
            archivo_nombre="doc_"+datetime.now().strftime("%Y%m%d%H%M%S_")+secure_filename(archivo.filename)
            archivo.save(UPLOAD_FOLDER / archivo_nombre)
        with conectar() as con:
            con.execute("""INSERT INTO movimientos(expediente_id,usuario_id,titulo,fecha,estatus,proxima_accion,fecha_limite,observaciones,archivo,creado_en) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (expediente_id,u["id"],request.form["titulo"],request.form["fecha"],request.form["estatus"],request.form["proxima_accion"],request.form["fecha_limite"],request.form["observaciones"],archivo_nombre,datetime.now().strftime("%Y-%m-%d %H:%M")))
            con.commit()
        flash("Movimiento guardado.")
        return redirect(url_for("expediente", id=expediente_id))
    contenido = """
    <div class="card"><h2>Agregar promoción / escrito</h2>
    <form method="post" enctype="multipart/form-data">
    <label>Título</label><input name="titulo" required>
    <label>Fecha</label><input type="date" name="fecha">
    <label>Estatus</label><select name="estatus"><option>Elaborado</option><option>Presentado</option><option>Acordado</option><option>Pendiente</option><option>Vencido</option><option>Concluido</option></select>
    <label>Próxima acción</label><input name="proxima_accion">
    <label>Fecha límite / audiencia</label><input type="date" name="fecha_limite">
    <label>Observaciones</label><textarea name="observaciones" rows="4"></textarea>
    <label>Archivo PDF, Word o imagen</label><input type="file" name="archivo">
    <button>Guardar</button></form></div>
    """
    return render(contenido)

@app.route("/vencimientos")
def vencimientos():
    if not requiere_login(): return redirect(url_for("login"))
    u=usuario_actual()
    with conectar() as con:
        if u["rol"]=="Administrador":
            datos=con.execute("""SELECT m.*,e.numero,e.tipo FROM movimientos m JOIN expedientes e ON e.id=m.expediente_id WHERE m.fecha_limite IS NOT NULL AND m.fecha_limite!='' ORDER BY m.fecha_limite""").fetchall()
        else:
            datos=con.execute("""SELECT m.*,e.numero,e.tipo FROM movimientos m JOIN expedientes e ON e.id=m.expediente_id LEFT JOIN expedientes_compartidos c ON c.expediente_id=e.id WHERE m.fecha_limite IS NOT NULL AND m.fecha_limite!='' AND (e.propietario_id=? OR c.usuario_id=?) ORDER BY m.fecha_limite""",(u["id"],u["id"])).fetchall()
    contenido = """
    <div class="card"><h2>Vencimientos</h2><table><tr><th>Fecha límite</th><th>Expediente</th><th>Tipo</th><th>Movimiento</th><th>Estatus</th><th>Próxima acción</th></tr>
    {% for d in datos %}<tr><td>{{d.fecha_limite}}</td><td><a href="/expediente/{{d.expediente_id}}">{{d.numero}}</a></td><td>{{d.tipo}}</td><td>{{d.titulo}}</td><td><span class="tag {{d.estatus.replace(' ','-')}}">{{d.estatus}}</span></td><td>{{d.proxima_accion}}</td></tr>{% endfor %}
    </table></div>
    """
    return render(contenido, datos=datos)

@app.route("/jurisprudencia")
def jurisprudencia():
    if not requiere_login(): return redirect(url_for("login"))
    q=request.args.get("q","").strip()
    scjn=SCJN_BUSCADOR + ("?q="+quote_plus(q) if q else "")
    sjf=SCJN_TESIS + ("?q="+quote_plus(q) if q else "")
    contenido = """
    <div class="card">
        <h2>Jurisprudencia y enlaces oficiales</h2>
        <form method="get"><label>Buscar concepto</label><input name="q" value="{{q}}" placeholder="Ejemplo: negativa ficta, daño patrimonial, prescripción"><button>Preparar búsqueda</button></form>
        {% if q %}<p>Búsqueda preparada: <b>{{q}}</b></p><a class="btn btnGold" target="_blank" href="{{scjn}}">Buscar en SCJN</a> <a class="btn btnGold" target="_blank" href="{{sjf}}">Buscar tesis</a>{% endif %}
    </div>
    <div class="card">
        <h2>Tribunales y boletines</h2>
        <a class="btn btn2" target="_blank" href="{{BOLETIN_PJBC}}">Boletín Judicial BC</a>
        <a class="btn btn2" target="_blank" href="{{PJBC_PORTAL}}">Tribunal / Poder Judicial BC</a>
        <a class="btn btn2" target="_blank" href="{{TEJA_BC}}">TEJA BC</a>
        <a class="btn btn2" target="_blank" href="{{TEJA_LISTAS}}">Listas TEJA</a>
        <a class="btn btnGold" target="_blank" href="{{SCJN_BUSCADOR}}">Buscador Jurídico SCJN</a>
        <a class="btn btnGold" target="_blank" href="{{SCJN_TESIS}}">Semanario Judicial</a>
    </div>
    """
    return render(contenido, q=q, scjn=scjn, sjf=sjf, BOLETIN_PJBC=BOLETIN_PJBC, PJBC_PORTAL=PJBC_PORTAL, TEJA_BC=TEJA_BC, TEJA_LISTAS=TEJA_LISTAS, SCJN_BUSCADOR=SCJN_BUSCADOR, SCJN_TESIS=SCJN_TESIS)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
