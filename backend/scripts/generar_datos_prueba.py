"""Genera los 5 CSV de prueba en datos_prueba/ con la suciedad tipica de
archivos reales. Determinista (misma semilla, mismos archivos).

Uso: .venv/Scripts/python.exe backend/scripts/generar_datos_prueba.py [directorio]

Suciedad por archivo (ver datos_prueba/README.md):
- vendedores.csv   UTF-8, coma. Nombres con espacios sobrantes, emails vacios.
- productos.csv    latin-1, punto y coma, precios con coma decimal y punto de
                   miles ("1.250,50"), nombres con enie y tildes, activo Si/No.
- medios_pago.csv  UTF-8 con BOM, coma.
- ventas.csv       UTF-8, coma. Encabezados en CamelCase y con espacios, fechas
                   en tres formatos mezclados, vendedores vacios y huerfanos,
                   productos huerfanos, algunos importes con "$ ".
- pagos.csv        UTF-8, punto y coma, DOS filas de titulo antes del
                   encabezado, montos con coma decimal, fechas dd/mm/aaaa,
                   ventas huerfanas.
"""
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

SEMILLA = 20260908
RAIZ_REPO = Path(__file__).resolve().parents[2]
DIRECTORIO_POR_DEFECTO = RAIZ_REPO / "datos_prueba"

SUCURSALES = ["Centro", "Norte", "Oeste"]

VENDEDORES = [
    (1, "María Pérez", "Centro", "2019-03-11", "maria.perez@tienda.com.ar"),
    (2, "Juan Gómez ", "Centro", "2020-07-01", "juan.gomez@tienda.com.ar"),
    (3, "Lucía Fernández", "Norte", "2018-11-20", ""),
    (4, " Carlos Rodríguez", "Norte", "2021-02-15", "carlos.rodriguez@tienda.com.ar"),
    (5, "Ana Martínez", "Oeste", "2017-05-02", "ana.martinez@tienda.com.ar"),
    (6, "Diego López", "Oeste", "2022-09-12", "diego.lopez@tienda.com.ar"),
    (7, "Sofía Díaz", "Centro", "2023-01-09", ""),
    (8, "Martín Sánchez", "Norte", "2016-08-23", "martin.sanchez@tienda.com.ar"),
    (9, "Valentina Romero", "Oeste", "2024-03-04", "valentina.romero@tienda.com.ar"),
    (10, "Nicolás Álvarez", "Centro", "2020-10-30", "nicolas.alvarez@tienda.com.ar"),
    (11, "Camila Torres", "Norte", "2025-02-17", "camila.torres@tienda.com.ar"),
    (12, "Federico Ruiz", "Oeste", "2019-12-02", ""),
]

PRODUCTOS = [
    ("Yerba Mate Cachamai 1kg", "Almacén", 4850.00),
    ("Azúcar Ledesma 1kg", "Almacén", 1320.50),
    ("Aceite Girasol Cañuelas 1,5L", "Almacén", 3990.00),
    ("Arroz Gallo Oro 1kg", "Almacén", 2150.00),
    ("Fideos Matarazzo 500g", "Almacén", 1480.00),
    ("Harina 000 Pureza 1kg", "Almacén", 990.90),
    ("Dulce de Leche Ñandú 400g", "Almacén", 2790.00),
    ("Café La Virginia 250g", "Almacén", 5600.00),
    ("Galletitas Criollitas 300g", "Almacén", 1850.00),
    ("Mermelada Arcor Durazno 454g", "Almacén", 2320.00),
    ("Gaseosa Coca-Cola 2,25L", "Bebidas", 3450.00),
    ("Agua Villavicencio 2L", "Bebidas", 1290.00),
    ("Cerveza Quilmes 1L", "Bebidas", 2980.00),
    ("Vino Malbec Trapiche 750ml", "Bebidas", 6900.00),
    ("Jugo Cepita Naranja 1L", "Bebidas", 2100.00),
    ("Fernet Branca 750ml", "Bebidas", 14500.00),
    ("Lavandina Ayudín 1L", "Limpieza", 1650.00),
    ("Detergente Magistral 750ml", "Limpieza", 2890.00),
    ("Jabón en polvo Skip 800g", "Limpieza", 6100.00),
    ("Esponja Mortimer", "Limpieza", 780.00),
    ("Papel higiénico Elite x4", "Limpieza", 3200.00),
    ("Desodorante ambiente Poett", "Limpieza", 2450.00),
    ("Shampoo Sedal 340ml", "Perfumería", 3980.00),
    ("Jabón Dove 90g", "Perfumería", 1490.00),
    ("Pasta dental Colgate 90g", "Perfumería", 2650.00),
    ("Desodorante Rexona 150ml", "Perfumería", 3750.00),
    ("Crema Nivea 100ml", "Perfumería", 4200.00),
    ("Jamón cocido Paladini x kg", "Fiambrería", 12900.00),
    ("Queso Cremoso La Serenísima x kg", "Fiambrería", 9800.00),
    ("Salame Milán x kg", "Fiambrería", 15400.00),
    ("Mortadela Cagnoli x kg", "Fiambrería", 6300.00),
    ("Queso Sardo x kg", "Fiambrería", 17600.00),
    ("Pan Lactal Bimbo 500g", "Panadería", 3100.00),
    ("Facturas x docena", "Panadería", 6000.00),
    ("Pan francés x kg", "Panadería", 2400.00),
    ("Medialunas x 6", "Panadería", 3600.00),
    ("Bizcochos Don Satur", "Panadería", 1950.00),
    ("Prepizza x 2", "Panadería", 3300.00),
    ("Tostadas Riera 200g", "Panadería", 1700.00),
    ("Budín de vainilla", "Panadería", 4100.00),
]

MEDIOS_PAGO = [
    (1, "Efectivo", "efectivo", 0),
    (2, "Tarjeta de débito", "tarjeta", 1),
    (3, "Tarjeta de crédito", "tarjeta", 12),
    (4, "Transferencia", "transferencia", 0),
    (5, "Mercado Pago", "billetera", 1),
    (6, "Cuenta corriente", "credito_interno", 1),
]

FECHA_INICIO = date(2025, 9, 1)
DIAS = 365
CANTIDAD_VENTAS = 3000


def _coma_decimal(valor: float) -> str:
    """1250.5 -> '1.250,50' (formato es-AR con punto de miles)."""
    entero, decimales = f"{valor:.2f}".split(".")
    entero_con_miles = f"{int(entero):,}".replace(",", ".")
    return f"{entero_con_miles},{decimales}"


def _fecha_mezclada(fecha: date, azar: random.Random) -> str:
    sorteo = azar.random()
    if sorteo < 0.70:
        return fecha.isoformat()
    if sorteo < 0.95:
        return fecha.strftime("%d/%m/%Y")
    return f"{fecha.day}/{fecha.month}/{fecha.year}"


def generar(directorio: Path) -> dict[str, Path]:
    """Escribe los 5 archivos y devuelve {nombre: ruta}."""
    directorio.mkdir(parents=True, exist_ok=True)
    azar = random.Random(SEMILLA)
    rutas = {}

    # vendedores.csv: UTF-8, coma
    ruta = directorio / "vendedores.csv"
    with open(ruta, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["id_vendedor", "nombre", "sucursal", "fecha_ingreso", "email"])
        escritor.writerows(VENDEDORES)
    rutas["vendedores"] = ruta

    # productos.csv: latin-1, punto y coma, coma decimal
    ruta = directorio / "productos.csv"
    with open(ruta, "w", encoding="latin-1", newline="") as archivo:
        escritor = csv.writer(archivo, delimiter=";")
        escritor.writerow(["id_producto", "nombre", "categoria", "precio_lista", "activo"])
        for indice, (nombre, categoria, precio) in enumerate(PRODUCTOS, start=1):
            activo = "No" if indice % 13 == 0 else "Si"
            escritor.writerow([indice, nombre, categoria, _coma_decimal(precio), activo])
    rutas["productos"] = ruta

    # medios_pago.csv: UTF-8 con BOM
    ruta = directorio / "medios_pago.csv"
    with open(ruta, "w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["id_medio_pago", "nombre", "tipo", "cuotas_max"])
        escritor.writerows(MEDIOS_PAGO)
    rutas["medios_pago"] = ruta

    # ventas.csv: UTF-8, coma, encabezados feos, fechas mezcladas, huerfanos
    ventas = []
    for id_venta in range(1, CANTIDAD_VENTAS + 1):
        fecha = FECHA_INICIO + timedelta(days=azar.randrange(DIAS))
        sorteo = azar.random()
        if sorteo < 0.03:
            id_vendedor = ""
        elif sorteo < 0.05:
            id_vendedor = 99  # huerfano
        else:
            id_vendedor = azar.randint(1, len(VENDEDORES))
        id_producto = 999 if azar.random() < 0.01 else azar.randint(1, len(PRODUCTOS))
        precio_base = PRODUCTOS[id_producto - 1][2] if id_producto != 999 else 1000.0
        precio_unitario = round(precio_base * azar.uniform(0.95, 1.10), 2)
        cantidad = azar.choice([1, 1, 1, 2, 2, 3, 4, 6, 12])
        importe = round(precio_unitario * cantidad, 2)
        importe_texto = f"$ {importe:.2f}" if azar.random() < 0.02 else f"{importe:.2f}"
        ventas.append((id_venta, fecha, id_vendedor, id_producto, cantidad, precio_unitario, importe, importe_texto))
    ruta = directorio / "ventas.csv"
    with open(ruta, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["IdVenta", "Fecha", "Vendedor", "IdProducto", "Cantidad", "Precio Unitario", "Importe"])
        for id_venta, fecha, id_vendedor, id_producto, cantidad, precio_unitario, _, importe_texto in ventas:
            escritor.writerow(
                [id_venta, _fecha_mezclada(fecha, azar), id_vendedor, id_producto, cantidad, f"{precio_unitario:.2f}", importe_texto]
            )
    rutas["ventas"] = ruta

    # pagos.csv: punto y coma, dos filas de titulo, coma decimal, fechas dd/mm/aaaa
    ruta = directorio / "pagos.csv"
    with open(ruta, "w", encoding="utf-8", newline="") as archivo:
        archivo.write("Listado de pagos - Sistema Caja v3\n")
        archivo.write("Exportado: 01/09/2026 10:32\n")
        escritor = csv.writer(archivo, delimiter=";")
        escritor.writerow(["id_pago", "id_venta", "id_medio_pago", "fecha_pago", "monto", "cuotas"])
        id_pago = 0
        for id_venta, fecha, _, _, _, _, importe, _ in ventas:
            partes = 2 if azar.random() < 0.10 else 1
            montos = [importe] if partes == 1 else [round(importe * 0.6, 2), round(importe * 0.4, 2)]
            for monto in montos:
                id_pago += 1
                id_venta_pago = 99999 if azar.random() < 0.01 else id_venta
                id_medio = azar.choices([1, 2, 3, 4, 5, 6], weights=[30, 25, 20, 12, 10, 3])[0]
                cuotas = azar.choice([1, 3, 6, 12]) if id_medio == 3 else 1
                fecha_pago = fecha + timedelta(days=azar.randint(0, 3))
                escritor.writerow(
                    [id_pago, id_venta_pago, id_medio, fecha_pago.strftime("%d/%m/%Y"), _coma_decimal(monto), cuotas]
                )
    rutas["pagos"] = ruta

    return rutas


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else DIRECTORIO_POR_DEFECTO
    for nombre, ruta in generar(destino).items():
        print(f"{nombre:14s} {ruta} ({ruta.stat().st_size:,} bytes)")
