import os
import sqlite3
import json
from datetime import datetime
from flask import Flask, send_from_directory, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__, static_folder='templates')

G# Toma la clave de Render si existe, o usa el valor por defecto si pruebas localmente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "TU_NUEVA_API_KEY_AQUI")
client = genai.Client(api_key=GEMINI_API_KEY)

def init_db():
    conn = sqlite3.connect('inventario.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS laptops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            modelo TEXT,
            specs TEXT,
            costo REAL,
            precio REAL,
            ganancia REAL,
            estado TEXT DEFAULT 'En Stock',
            fecha_ingreso TEXT,
            fecha_venta TEXT DEFAULT '-'
        )
    ''')
    try:
        cursor.execute("ALTER TABLE laptops ADD COLUMN fecha_ingreso TEXT")
    except:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT,
            fecha_generacion TEXT,
            fecha_inicio TEXT,
            fecha_fin TEXT,
            contenido TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def safe_float(val):
    try:
        if val is None or val == '':
            return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/api/laptops', methods=['GET'])
def get_laptops():
    conn = sqlite3.connect('inventario.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM laptops ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify([{
        'id': r[0], 'codigo': r[1], 'modelo': r[2], 'specs': r[3],
        'costo': r[4], 'precio': r[5], 'ganancia': r[6],
        'estado': r[7], 'fecha_ingreso': r[8] if len(r) > 8 else '-', 'fecha_venta': r[9] if len(r) > 9 else '-'
    } for r in rows])

@app.route('/api/procesar-foto', methods=['POST'])
def procesar_foto():
    if 'imagen' not in request.files:
        return jsonify({'error': 'No se envió imagen'}), 400
    
    file = request.files['imagen']
    image_bytes = file.read()
    
    prompt = """Analiza la imagen de la laptop o etiqueta de especificaciones y extrae la información.
    Responde ÚNICAMENTE en JSON válido con la siguiente estructura exacta:
    {
      "modelo": "Marca y modelo comercial del equipo (ej: Dell Inspiron 5502)",
      "specs": "i5 11va (i5-1135G7) / 16GB RAM / 512GB SSD",
      "costo": 0,
      "precio": 0
    }
    
    Reglas para "specs":
    - Procesador con generación y modelo exacto entre paréntesis (ej: "i5 11va (i5-1135G7)", "Ryzen 5 (R5-5500U)").
    - RAM en GB.
    - Almacenamiento redondeado a capacidades estándar: 128GB, 256GB, 512GB, 1TB o 2TB SSD.
    - Junta todo en una sola línea separada por slashes '/'.
    
    Para costo y precio coloca solo números decimales o 0 si no están visibles."""

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=file.content_type), prompt]
        )
        
        # Limpiar bloques de código Markdown ```json ... ``` si los genera la IA
        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()
        
        res_json = json.loads(raw_text)
        
        return jsonify({
            'modelo': str(res_json.get('modelo', '')),
            'specs': str(res_json.get('specs', '')),
            'costo': safe_float(res_json.get('costo', 0)),
            'precio': safe_float(res_json.get('precio', 0))
        })
    except Exception as e:
        print("Error en procesar-foto:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/agregar', methods=['POST'])
def agregar():
    try:
        data = request.json or {}
        costo = safe_float(data.get('costo'))
        precio = safe_float(data.get('precio'))
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect('inventario.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM laptops')
        count = cursor.fetchone()[0] + 1
        
        cursor.execute('''
            INSERT INTO laptops (codigo, modelo, specs, costo, precio, ganancia, estado, fecha_ingreso, fecha_venta)
            VALUES (?, ?, ?, ?, ?, ?, 'En Stock', ?, '-')
        ''', (f"LAP-{count:03d}", data.get('modelo', 'Sin Modelo'), data.get('specs', ''), costo, precio, precio - costo, fecha_hoy))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        print("Error en agregar:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/editar/<int:laptop_id>', methods=['POST'])
def editar(laptop_id):
    try:
        data = request.json or {}
        costo = safe_float(data.get('costo'))
        precio = safe_float(data.get('precio'))
        
        conn = sqlite3.connect('inventario.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE laptops 
            SET modelo=?, specs=?, costo=?, precio=?, ganancia=?, estado=?, fecha_ingreso=?, fecha_venta=?
            WHERE id=?
        ''', (data.get('modelo', ''), data.get('specs', ''), costo, precio, precio - costo, data.get('estado', 'En Stock'), data.get('fecha_ingreso', '-'), data.get('fecha_venta', '-'), laptop_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/eliminar/<int:laptop_id>', methods=['DELETE'])
def eliminar(laptop_id):
    conn = sqlite3.connect('inventario.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM laptops WHERE id=?', (laptop_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/vender/<int:laptop_id>', methods=['POST'])
def vender(laptop_id):
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect('inventario.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE laptops 
        SET estado = 'Vendido', fecha_venta = ? 
        WHERE id = ?
    ''', (fecha_hoy, laptop_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/reporte/generar', methods=['POST'])
def generar_reporte():
    try:
        data = request.json or {}
        f_inicio = data.get('inicio')
        f_fin = data.get('fin')
        
        if not f_inicio or not f_fin:
            return jsonify({'error': 'Debes seleccionar un rango de fechas válido'}), 400

        conn = sqlite3.connect('inventario.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT codigo, modelo, specs, costo, precio, ganancia, fecha_ingreso, fecha_venta 
            FROM laptops 
            WHERE estado = 'Vendido' AND fecha_venta BETWEEN ? AND ?
        ''', (f_inicio, f_fin))
        vendidas = cursor.fetchall()

        if not vendidas:
            texto_reporte = f"""==================================================
REPORTE DE VENTAS ({f_inicio} a {f_fin})
==================================================

RESUMEN GENERAL:
- Total Unidades Vendidas: 0
- Inversión Recuperada: $0.00
- Total Facturado: $0.00
- Ganancia Neta Total: $0.00

DETALLE DE VENTAS:
No se registraron ventas de laptops en el rango de fechas seleccionado.
"""
        else:
            prompt = f"""Genera un reporte ejecutivo simplificado y profesional para mi jefe correspondiente al periodo {f_inicio} al {f_fin}.
            
            Ventas realizadas:
            {json.dumps(vendidas)}

            Estructura la respuesta usando ÚNICAMENTE este formato de texto claro y tablas simplificadas:

            ==================================================
            REPORTE DE VENTAS ({f_inicio} a {f_fin})
            ==================================================

            RESUMEN GENERAL:
            - Total Unidades Vendidas: [Número]
            - Inversión Recuperada: $[Monto]
            - Total Facturado: $[Monto]
            - Ganancia Neta Total: $[Monto]

            DETALLE DE VENTAS:
            | CÓDIGO | MODELO | COSTO | VENTA | GANANCIA | FECHA VENTA |
            |---|---|---|---|---|---|
            [Rellena cada fila de los equipos vendidos]

            MÉTRICAS CLAVE:
            - Equipo más rentable: [Modelo y ganancia]
            - Estado de inventario general al cierre.
            """

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            texto_reporte = response.text

        fecha_gen = datetime.now().strftime('%Y-%m-%d %H:%M')
        titulo = f"Reporte ({f_inicio} al {f_fin})"
        
        cursor.execute('''
            INSERT INTO reportes (titulo, fecha_generacion, fecha_inicio, fecha_fin, contenido)
            VALUES (?, ?, ?, ?, ?)
        ''', (titulo, fecha_gen, f_inicio, f_fin, texto_reporte))
        
        reporte_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'id': reporte_id,
            'titulo': titulo,
            'fecha_generacion': fecha_gen,
            'fecha_inicio': f_inicio,
            'fecha_fin': f_fin,
            'contenido': texto_reporte
        })

    except Exception as e:
        error_msg = str(e)
        if "503" in error_msg or "high demand" in error_msg:
            return jsonify({'error': 'Los servidores de la IA están muy ocupados en este momento. Por favor, espera 30 segundos e inténtalo de nuevo.'}), 500
        return jsonify({'error': f'Error de conexión: {error_msg}'}), 500

@app.route('/api/reportes', methods=['GET'])
def listar_reportes():
    conn = sqlite3.connect('inventario.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, titulo, fecha_generacion, fecha_inicio, fecha_fin, contenido FROM reportes ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify([{
        'id': r[0], 'titulo': r[1], 'fecha_generacion': r[2],
        'fecha_inicio': r[3], 'fecha_fin': r[4], 'contenido': r[5]
    } for r in rows])

@app.route('/api/reportes/eliminar/<int:reporte_id>', methods=['DELETE'])
def eliminar_reporte(reporte_id):
    try:
        conn = sqlite3.connect('inventario.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM reportes WHERE id = ?', (reporte_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)