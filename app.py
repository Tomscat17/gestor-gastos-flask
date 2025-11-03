import sqlite3
import datetime
# --- ¡CAMBIOS EN IMPORTS! ---
import psycopg2
import psycopg2.extras # Para que los cursores devuelvan diccionarios
import os # Para leer la URL de la base de datos
# --- Fin de cambios ---
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import calendar 
import locale 
import click 
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_bcrypt import Bcrypt

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mi-llave-secreta-muy-segura-12345'
# --- ¡CAMBIO CRÍTICO! ---
# Render nos dará la URL de la base de datos en esta variable de entorno.
DATABASE_URL = os.environ.get('DATABASE_URL')
# --- Fin del cambio ---

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' 
login_manager.login_message = 'Por favor, inicia sesión para acceder a esta página.'
login_manager.login_message_category = 'info' 

class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # ¡MODIFICADO! (%s en lugar de ?)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_db = cursor.fetchone()
    conn.close()
    if user_db:
        return User(id=user_db['id'], email=user_db['email'])
    return None

@app.context_processor
def inject_global_vars():
    categorias = []
    if current_user.is_authenticated:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # ¡MODIFICADO! (%s en lugar de ?)
            cursor.execute("SELECT nombre FROM categorias WHERE user_id = %s ORDER BY nombre ASC", (current_user.id,))
            categorias = [row['nombre'] for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            print(f"ADVERTENCIA: No se pudieron cargar las categorías. Error: {e}")
            
    return dict(
        categorias_globales=categorias
    )

@app.template_filter('currency')
def format_currency_filter(value):
    try:
        formatted_value = f"${int(value):,d}"
        return formatted_value.replace(",", ".")
    except (ValueError, TypeError):
        try:
            formatted_value = f"${value:,.0f}"
            return formatted_value.replace(",", ".")
        except Exception:
            return value

def set_locale():
    try:
        locales_to_try = ['es_ES.UTF-8', 'es_ES', 'spanish', 'es-CL.UTF-8', 'es-CL']
        for loc in locales_to_try:
            try:
                locale.setlocale(locale.LC_TIME, loc)
                return True
            except locale.Error:
                continue
    except Exception:
        pass
    return False

# --- ¡FUNCIÓN COMPLETAMENTE REESCRITA! ---
def get_db_connection():
    """Se conecta a la base de datos PostgreSQL usando la URL del entorno."""
    conn = psycopg2.connect(DATABASE_URL)
    # ¡Devuelve un cursor que funciona como un diccionario! (reemplaza a row_factory)
    conn.cursor_factory = psycopg2.extras.DictCursor
    return conn

# --- ¡FUNCIÓN COMPLETAMENTE REESCRITA! ---
def create_default_categories(user_id):
    default_categories = [
        ('Comida', user_id), ('Transporte', user_id), ('Vivienda', user_id), ('Ocio', user_id), 
        ('Salud', user_id), ('Ropa', user_id), ('Educación', user_id), ('Impuestos', user_id), ('Otros', user_id)
    ]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # ¡MODIFICADO! (%s en lugar de ?)
        cursor.executemany("INSERT INTO categorias (nombre, user_id) VALUES (%s, %s)", default_categories)
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Categorías por defecto creadas para el user {user_id}.")
    except Exception as e:
        print(f"Error creando categorías por defecto: {e}")

# --- ¡FUNCIÓN COMPLETAMENTE REESCRITA! (Sintaxis SQL de PostgreSQL) ---
def init_db_logic():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Sintaxis de PostgreSQL (SERIAL PRIMARY KEY, VARCHAR)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transacciones (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            descripcion VARCHAR(255) NOT NULL,
            monto DECIMAL(10, 2) NOT NULL,
            tipo VARCHAR(10) NOT NULL CHECK(tipo IN ('ingreso', 'gasto')),
            categoria VARCHAR(100) DEFAULT 'Otros',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS presupuestos (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            categoria VARCHAR(100) NOT NULL,
            monto_maximo DECIMAL(10, 2) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, categoria)
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS categorias (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            nombre VARCHAR(100) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, nombre)
        )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Database initialized/migrated successfully.")
    except Exception as e:
        print(f"An error occurred while initializing the DB: {e}")

@app.cli.command('init-db')
def init_db_command():
    init_db_logic()
    click.echo('Base de datos inicializada.')

set_locale()

# --- Rutas de Autenticación (¡MODIFICADAS A %s!) ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Las contraseñas no coinciden. Por favor, inténtalo de nuevo.', 'danger')
            return redirect(url_for('register'))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user_db = cursor.fetchone()

        if user_db:
            flash('Este email ya está registrado. Por favor, inicia sesión.', 'warning')
            cursor.close()
            conn.close()
            return redirect(url_for('login'))
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        try:
            cursor.execute("INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id", (email, hashed_password))
            new_user_id = cursor.fetchone()['id']
            conn.commit()
            
            create_default_categories(new_user_id)
            
            flash('¡Cuenta creada con éxito! Ahora puedes iniciar sesión.', 'success')
        except Exception as e:
            flash(f'Error al registrar: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()
            
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user_db = cursor.fetchone()
        conn.close()
        
        if user_db and bcrypt.check_password_hash(user_db['password_hash'], password):
            user_obj = User(id=user_db['id'], email=user_db['email'])
            login_user(user_obj, remember=True)
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Email o contraseña incorrectos. Por favor, inténtalo de nuevo.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión.', 'success')
    return redirect(url_for('login'))


# --- Rutas Principales (¡MODIFICADAS A %s!) ---
@app.route('/', methods=['GET', 'POST'])
@login_required 
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = current_user.id 

    if request.method == 'POST':
        try:
            fecha = request.form['fecha']
            descripcion = request.form['descripcion']
            monto = float(request.form['monto'])
            tipo = request.form['tipo']
            categoria = request.form.get('categoria', 'Otros') if tipo == 'gasto' else 'Ingreso'
            cursor.execute(
                "INSERT INTO transacciones (fecha, descripcion, monto, tipo, categoria, user_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (fecha, descripcion, monto, tipo, categoria, user_id)
            )
            conn.commit()
        except Exception as e:
            print(f"An error occurred while inserting data: {e}")
        finally:
            cursor.close()
            conn.close()
        new_fecha_dt = datetime.datetime.strptime(fecha, '%Y-%m-%d')
        return redirect(url_for('index', mes=f"{new_fecha_dt.month:02d}", ano=new_fecha_dt.year))

    # Lógica GET
    today = datetime.date.today()
    mes_seleccionado = request.args.get('mes', f"{today.month:02d}")
    ano_seleccionado = request.args.get('ano', str(today.year))
    filtro_mensual_sql_where = " WHERE strftime('%Y', fecha) = %s AND strftime('%m', fecha) = %s AND user_id = %s "
    filtro_mensual_sql_and = " AND strftime('%Y', fecha) = %s AND strftime('%m', fecha) = %s AND user_id = %s "
    params_mensual = (ano_seleccionado, mes_seleccionado, user_id)
    
    progreso_presupuestos = []
    transacciones = []
    balance_mensual, ingresos_mensual, gastos_mensual = 0.0, 0.0, 0.0
    balance_historico = 0.0
    
    try:
        cursor.execute("SELECT * FROM transacciones" + filtro_mensual_sql_where + "ORDER BY fecha DESC, id DESC", params_mensual)
        transacciones = cursor.fetchall()
        cursor.execute("SELECT COALESCE(SUM(monto), 0) FROM transacciones WHERE tipo = 'ingreso'" + filtro_mensual_sql_and, params_mensual)
        ingresos_mensual = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(monto), 0) FROM transacciones WHERE tipo = 'gasto'" + filtro_mensual_sql_and, params_mensual)
        gastos_mensual = cursor.fetchone()[0]
        balance_mensual = ingresos_mensual - gastos_mensual

        cursor.execute("SELECT COALESCE(SUM(monto), 0) FROM transacciones WHERE tipo = 'ingreso' AND user_id = %s", (user_id,))
        total_ingresos_historico = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(monto), 0) FROM transacciones WHERE tipo = 'gasto' AND user_id = %s", (user_id,))
        total_gastos_historico = cursor.fetchone()[0]
        balance_historico = total_ingresos_historico - total_gastos_historico
        
        cursor.execute(
            "SELECT categoria, SUM(monto) as total_gastado "
            "FROM transacciones "
            "WHERE tipo = 'gasto'" + filtro_mensual_sql_and +
            "GROUP BY categoria",
            params_mensual
        )
        gastos_reales = {row['categoria']: row['total_gastado'] for row in cursor.fetchall()}

        cursor.execute("SELECT categoria, monto_maximo FROM presupuestos WHERE user_id = %s", (user_id,))
        presupuestos_fijados = {row['categoria']: row['monto_maximo'] for row in cursor.fetchall()}

        cursor.execute("SELECT nombre FROM categorias WHERE user_id = %s ORDER BY nombre ASC", (user_id,))
        categorias_db = [row['nombre'] for row in cursor.fetchall()]

        for cat in categorias_db: 
            gastado = gastos_reales.get(cat, 0)
            presupuesto = presupuestos_fijados.get(cat, 0)
            if presupuesto > 0:
                porcentaje, porcentaje_real = min(round((float(gastado) / float(presupuesto)) * 100), 100), round((float(gastado) / float(presupuesto)) * 100)
            else:
                porcentaje, porcentaje_real = 0, 0
            progreso_presupuestos.append({'categoria': cat, 'gastado': gastado, 'presupuesto': presupuesto, 'porcentaje': porcentaje, 'porcentaje_real': porcentaje_real})

    except Exception as e:
        print(f"An error occurred while fetching data: {e}")
    finally:
        cursor.close()
        conn.close()
    
    if ano_seleccionado == str(today.year) and mes_seleccionado == f"{today.month:02d}":
        default_form_date = today.strftime('%Y-%m-%d')
    else:
        default_form_date = f"{ano_seleccionado}-{mes_seleccionado}-01"
    
    nombres_meses_default = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    if not set_locale(): nombres_meses = nombres_meses_default
    else:
        try: nombres_meses = list(calendar.month_name)[1:]
        except Exception: nombres_meses = nombres_meses_default

    meses_del_ano = [{"val": f"{i:02d}", "nom": nombres_meses[i-1]} for i in range(1, 13)]
    anos_disponibles = list(range(today.year - 5, today.year + 2))
    
    return render_template('index.html', 
                           transacciones=transacciones, 
                           balance_mensual=balance_mensual,
                           ingresos_mensual=ingresos_mensual,
                           gastos_mensual=gastos_mensual,
                           balance_historico=balance_historico, 
                           default_form_date=default_form_date,
                           mes_seleccionado=mes_seleccionado,
                           ano_seleccionado=ano_seleccionado,
                           meses_del_ano=meses_del_ano,
                           anos_disponibles=anos_disponibles,
                           progreso_presupuestos=progreso_presupuestos
                           )

@app.route('/presupuestos', methods=['GET', 'POST'])
@login_required
def presupuestos():
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = current_user.id

    if request.method == 'POST':
        try:
            categoria = request.form['categoria']
            monto_maximo = float(request.form['monto_maximo'])
            cursor.execute(
                """
                INSERT INTO presupuestos (categoria, monto_maximo, user_id)
                VALUES (%s, %s, %s)
                ON CONFLICT(user_id, categoria) DO UPDATE SET
                    monto_maximo = excluded.monto_maximo
                """,
                (categoria, monto_maximo, user_id)
            )
            conn.commit()
        except Exception as e:
            print(f"Error al guardar presupuesto: {e}")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('presupuestos'))

    presupuestos_guardados = []
    try:
        cursor.execute("SELECT categoria, monto_maximo FROM presupuestos WHERE user_id = %s ORDER BY categoria", (user_id,))
        presupuestos_guardados = cursor.fetchall()
    except Exception as e:
        print(f"Error al leer presupuestos: {e}")
    
    cursor.close()
    conn.close()
    presupuestos_dict = {p['categoria']: p['monto_maximo'] for p in presupuestos_guardados}
    return render_template('presupuestos.html', 
                           presupuestos_guardados=presupuestos_dict
                           )

@app.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion():
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = current_user.id

    if request.method == 'POST':
        categoria_nueva = request.form.get('nombre_categoria', '').strip()
        if categoria_nueva:
            try:
                cursor.execute("INSERT INTO categorias (nombre, user_id) VALUES (%s, %s)", (categoria_nueva, user_id))
                conn.commit()
            except Exception as e:
                conn.rollback()
                if 'UNIQUE constraint' in str(e):
                    flash(f"La categoría '{categoria_nueva}' ya existe.", 'warning')
                else:
                    flash(f"Error al insertar categoría: {e}", 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('configuracion'))

    cursor.close()
    conn.close()
    return render_template('configuracion.html')

@app.route('/configuracion/delete', methods=['POST'])
@login_required
def delete_categoria():
    categoria_a_borrar = request.form.get('categoria')
    user_id = current_user.id
    
    if categoria_a_borrar == 'Otros':
        flash("No se puede borrar la categoría 'Otros'.", 'warning')
        return redirect(url_for('configuracion'))
    if not categoria_a_borrar:
         return redirect(url_for('configuracion'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE transacciones SET categoria = 'Otros' WHERE categoria = %s AND user_id = %s",(categoria_a_borrar, user_id))
        cursor.execute("DELETE FROM presupuestos WHERE categoria = %s AND user_id = %s",(categoria_a_borrar, user_id))
        cursor.execute("DELETE FROM categorias WHERE nombre = %s AND user_id = %s",(categoria_a_borrar, user_id))
        conn.commit()
        flash(f"Categoría '{categoria_a_borrar}' eliminada.", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Error al eliminar categoría: {e}", 'danger')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('configuracion'))

@app.route('/reportes')
@login_required
def reportes():
    today = datetime.date.today()
    mes_seleccionado = request.args.get('mes', f"{today.month:02d}")
    ano_seleccionado = request.args.get('ano', str(today.year))

    nombres_meses_default = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    if not set_locale(): nombres_meses = nombres_meses_default
    else:
        try: nombres_meses = list(calendar.month_name)[1:]
        except Exception: nombres_meses = nombres_meses_default

    meses_del_ano = [{"val": f"{i:02d}", "nom": nombres_meses[i-1]} for i in range(1, 13)]
    anos_disponibles = list(range(today.year - 5, today.year + 2))

    return render_template('reportes.html',
                           mes_seleccionado=mes_seleccionado,
                           ano_seleccionado=ano_seleccionado,
                           meses_del_ano=meses_del_ano,
                           anos_disponibles=anos_disponibles)

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = current_user.id
    try:
        cursor.execute("DELETE FROM transacciones WHERE id = %s AND user_id = %s", (id, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"An error occurred while deleting data: {e}")
    finally:
        cursor.close()
        conn.close()
        return redirect(request.referrer or url_for('index'))

@app.route('/update/<int:id>', methods=['POST'])
@login_required
def update(id):
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        user_id = current_user.id
        try:
            cursor.execute("SELECT id FROM transacciones WHERE id = %s AND user_id = %s", (id, user_id))
            if cursor.fetchone():
                fecha = request.form['edit-fecha']
                descripcion = request.form['edit-descripcion']
                monto = float(request.form['edit-monto'])
                tipo = request.form['edit-tipo']
                categoria = request.form.get('edit-categoria', 'Otros') if tipo == 'gasto' else 'Ingreso'
                
                cursor.execute(
                    """
                    UPDATE transacciones SET fecha = %s, descripcion = %s, monto = %s, tipo = %s, categoria = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (fecha, descripcion, monto, tipo, categoria, id, user_id)
                )
                conn.commit()
            else:
                flash("Error: No tienes permiso para editar esta transacción.", 'danger')
        except Exception as e:
            conn.rollback()
            print(f"An error occurred while updating data: {e}")
        finally:
            cursor.close()
            conn.close()
        return redirect(request.referrer or url_for('index'))


# --- APIs de Gráficos (¡MODIFICADAS A %s!) ---
@app.route('/api/chart-data/daily-flow')
@login_required
def daily_flow_chart_data():
    mes = request.args.get('mes')
    ano = request.args.get('ano')
    user_id = current_user.id
    if not mes or not ano:
        today = datetime.date.today()
        mes, ano = f"{today.month:02d}", str(today.year)
    
    date_filter_sql_where = " WHERE strftime('%Y', fecha) = %s AND strftime('%m', fecha) = %s AND user_id = %s "
    params = (ano, mes, user_id)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT strftime('%d', fecha) as dia, tipo, SUM(monto) as total "
        "FROM transacciones" + date_filter_sql_where +
        "GROUP BY dia, tipo ORDER BY dia",
        params
    )
    data_db = cursor.fetchall()
    conn.close()
    num_dias = calendar.monthrange(int(ano), int(mes))[1]
    labels = [f"{i:02d}" for i in range(1, num_dias + 1)] 
    gastos_data, ingresos_data = [0] * num_dias, [0] * num_dias
    for row in data_db:
        dia_index = int(row['dia']) - 1
        if row['tipo'] == 'gasto':
            gastos_data[dia_index] = row['total']
        else:
            ingresos_data[dia_index] = row['total']
    return jsonify({'labels': labels, 'datasets': [{'label': 'Gastos', 'data': gastos_data, 'backgroundColor': '#FF6384'}, {'label': 'Ingresos', 'data': ingresos_data, 'backgroundColor': '#36A2EB'}]})

@app.route('/api/chart-data/categories')
@login_required
def category_chart_data():
    mes = request.args.get('mes')
    ano = request.args.get('ano')
    user_id = current_user.id
    if not mes or not ano:
        today = datetime.date.today()
        mes, ano = f"{today.month:02d}", str(today.year)

    date_filter_sql_and = " AND strftime('%Y', fecha) = %s AND strftime('%m', fecha) = %s AND user_id = %s "
    params = (ano, mes, user_id)
    
    gastos_por_categoria = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT categoria, SUM(monto) as total "
            "FROM transacciones "
            "WHERE tipo = 'gasto'" + date_filter_sql_and +
            "GROUP BY categoria HAVING total > 0 ORDER BY total DESC",
            params
        )
        gastos_por_categoria = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching category data: {e}")
    finally:
        if conn:
            conn.close()
    
    labels = [row['categoria'] for row in gastos_por_categoria]
    data = [row['total'] for row in gastos_por_categoria]
    return jsonify({'labels': labels, 'data': data})

@app.route('/api/chart-data/annual-flow')
@login_required
def annual_flow_chart_data():
    ano = request.args.get('ano')
    user_id = current_user.id
    if not ano:
        ano = str(datetime.date.today().year)

    nombres_meses_default = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    gastos_por_mes, ingresos_por_mes = [0] * 12, [0] * 12
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT strftime('%m', fecha) as mes, SUM(monto) as total "
            "FROM transacciones "
            "WHERE tipo = 'gasto' AND strftime('%Y', fecha) = %s AND user_id = %s "
            "GROUP BY mes",
            (ano, user_id)
        )
        for row in cursor.fetchall():
            gastos_por_mes[int(row['mes']) - 1] = float(row['total'])
            
        cursor.execute(
            "SELECT strftime('%m', fecha) as mes, SUM(monto) as total "
            "FROM transacciones "
            "WHERE tipo = 'ingreso' AND strftime('%Y', fecha) = %s AND user_id = %s "
            "GROUP BY mes",
            (ano, user_id)
        )
        for row in cursor.fetchall():
            ingresos_por_mes[int(row['mes']) - 1] = float(row['total'])
            
    except Exception as e:
        print(f"Error al obtener datos anuales: {e}")
    finally:
        if conn:
            conn.close()
            
    return jsonify({'labels': nombres_meses_default, 'datasets': [{'label': 'Gastos', 'data': gastos_por_mes, 'backgroundColor': '#FF6384'}, {'label': 'Ingresos', 'data': ingresos_por_mes, 'backgroundColor': '#36A2EB'}]})


if __name__ == '__main__':
    app.run(debug=True)