import { describe, expect, it } from "vitest";

import type { Campo, EntidadModelo, ModeloSemantico, RelacionModelo } from "../tipos";
import { ANCHO_CAJA, ESPACIO_HORIZONTAL, calcularLayout, ladosDeCardinalidad } from "./diagramaLayout";

function campo(id: string, tipo_semantico: Campo["tipo_semantico"] = "categoria", estado: Campo["estado"] = "confirmada"): Campo {
  return { id, columna_origen: id, nombre: id, tipo_dato: "texto", tipo_semantico, confianza: 1, origen: "usuario", estado, descripcion: null, evidencia: {} };
}

function entidad(id: string, tipo: EntidadModelo["tipo"], campos: Campo[], clave = [campos[0].id]): EntidadModelo {
  return { id, nombre: id, fuente: id, tipo, clave_primaria: clave, campos, sinonimos: [], descripcion: null, origen: "usuario" };
}

function relacion(id: string, desde: string, campoDesde: string, hacia: string, campoHacia: string, cardinalidad: RelacionModelo["cardinalidad"] = "n:1"): RelacionModelo {
  return { id, desde: { entidad: desde, campo: campoDesde }, hacia: { entidad: hacia, campo: campoHacia }, cardinalidad, confianza: 1, evidencia: {}, estado: "confirmada", propagar: true };
}

const MODELO: ModeloSemantico = {
  version: 1,
  entidades: [
    entidad("ventas", "hechos", [campo("id_venta", "identificador"), campo("id_vendedor", "clave_foranea")]),
    entidad("vendedores", "dimension", [campo("id_vendedor", "identificador"), campo("nombre")]),
  ],
  relaciones: [relacion("ventas_vendedor", "ventas", "id_vendedor", "vendedores", "id_vendedor", "n:1")],
  metricas: [],
  dimensiones_tiempo: [],
  umbral_confianza: 0.9,
};

describe("ladosDeCardinalidad", () => {
  it("n:1 es muchos->uno", () => {
    expect(ladosDeCardinalidad("n:1")).toEqual({ desde: "muchos", hacia: "uno" });
  });
  it("1:n es uno->muchos", () => {
    expect(ladosDeCardinalidad("1:n")).toEqual({ desde: "uno", hacia: "muchos" });
  });
  it("1:1 es uno->uno", () => {
    expect(ladosDeCardinalidad("1:1")).toEqual({ desde: "uno", hacia: "uno" });
  });
});

describe("calcularLayout", () => {
  it("pone la entidad de hechos en la primera capa y la dimension relacionada en la siguiente", () => {
    const layout = calcularLayout(MODELO);
    const ventas = layout.cajas.find((c) => c.entidad.id === "ventas")!;
    const vendedores = layout.cajas.find((c) => c.entidad.id === "vendedores")!;
    expect(ventas.x).toBe(0);
    expect(vendedores.x).toBe(ANCHO_CAJA + ESPACIO_HORIZONTAL);
  });

  it("arma un conector por relacion, con el lado 'muchos' del lado de la FK", () => {
    const layout = calcularLayout(MODELO);
    expect(layout.conectores).toHaveLength(1);
    const [conector] = layout.conectores;
    expect(conector.desde.lado).toBe("muchos");
    expect(conector.hacia.lado).toBe("uno");
  });

  it("marca como clave los campos que estan en clave_primaria", () => {
    const layout = calcularLayout(MODELO);
    const ventas = layout.cajas.find((c) => c.entidad.id === "ventas")!;
    expect(ventas.filas.find((f) => f.campo.id === "id_venta")?.esClave).toBe(true);
    expect(ventas.filas.find((f) => f.campo.id === "id_vendedor")?.esClave).toBe(false);
  });

  it("una entidad sin relaciones queda sola, sin romper el layout", () => {
    const modeloConSuelta: ModeloSemantico = {
      ...MODELO,
      entidades: [...MODELO.entidades, entidad("productos", "dimension", [campo("id_producto", "identificador")])],
    };
    const layout = calcularLayout(modeloConSuelta);
    expect(layout.cajas).toHaveLength(3);
    expect(layout.conectores).toHaveLength(1);
  });
});
