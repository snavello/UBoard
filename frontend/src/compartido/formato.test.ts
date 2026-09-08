import { describe, expect, it } from "vitest";

import { escribirFiltros, leerFiltros, serializarFiltros } from "./filtrosUrl";
import { etiquetaPeriodo, formatearCelda, formatearCompacto, formatearFecha, formatearMetrica } from "./formato";

describe("formato es-AR", () => {
  it("moneda con miles y sin decimales cuando es grande", () => {
    expect(formatearMetrica(48320027.9, "moneda")).toBe("$ 48.320.028");
    expect(formatearMetrica(1234.5, "moneda")).toBe("$ 1.234,50");
    expect(formatearMetrica(null, "moneda")).toBe("—");
  });
  it("entero, decimal y porcentaje", () => {
    expect(formatearMetrica(3000, "entero")).toBe("3.000");
    expect(formatearMetrica(16106.6759, "decimal")).toBe("16.106,68");
    expect(formatearMetrica(0.1234, "porcentaje")).toBe("12,3 %");
  });
  it("compacto para ejes", () => {
    expect(formatearCompacto(48320027, "moneda")).toBe("$ 48,3 M");
    expect(formatearCompacto(12500)).toBe("13 k");
    expect(formatearCompacto(950)).toBe("950");
  });
  it("fechas y periodos", () => {
    expect(formatearFecha("2026-03-05")).toBe("05/03/2026");
    expect(formatearFecha("2026-03-05T14:07:00Z")).toBe("05/03/2026 14:07");
    expect(etiquetaPeriodo("2026-03-01", "mes")).toBe("mar 2026");
    expect(etiquetaPeriodo("2026-04-01", "trimestre")).toBe("T2 2026");
    expect(etiquetaPeriodo("2026-01-01", "anio")).toBe("2026");
    expect(etiquetaPeriodo(null, "mes")).toBe("(sin dato)");
  });
  it("celdas por tipo", () => {
    expect(formatearCelda(true, "booleano")).toBe("Sí");
    expect(formatearCelda(1250.5, "decimal")).toBe("1.250,50");
    expect(formatearCelda(1250.5, "decimal", "moneda")).toBe("$ 1.250,50");
    expect(formatearCelda(null, "texto")).toBe("—");
  });
});

describe("filtros en la URL", () => {
  it("serializa solo lo activo", () => {
    expect(serializarFiltros({ f_sucursal: ["Centro"], f_vendedor: [], f_fecha: [null, null], f_x: null })).toBe('{"f_sucursal":["Centro"]}');
    expect(serializarFiltros({ f_fecha: ["2026-01-01", ""] })).toBe('{"f_fecha":["2026-01-01",null]}');
    expect(serializarFiltros({})).toBeNull();
  });
  it("lee y escribe los parametros", () => {
    const parametros = escribirFiltros(new URLSearchParams("otro=1"), { f_sucursal: ["Norte"] });
    expect(parametros.get("otro")).toBe("1");
    expect(leerFiltros(parametros)).toEqual({ f_sucursal: ["Norte"] });
    expect(leerFiltros(new URLSearchParams("filtros=basura"))).toEqual({});
    expect(escribirFiltros(parametros, {}).has("filtros")).toBe(false);
  });
});
