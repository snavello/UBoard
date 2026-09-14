import { describe, expect, it } from "vitest";

import { resumirDiffEsquema } from "./diff";
import type { DiffEsquema } from "../tipos";

function diff(parcial: Partial<DiffEsquema>): DiffEsquema {
  return {
    columnas_nuevas: [],
    columnas_perdidas: [],
    columnas_perdidas_en_uso: [],
    columnas_tipo_cambiado: [],
    filas_antes: 10,
    filas_despues: 10,
    ...parcial,
  };
}

describe("resumirDiffEsquema", () => {
  it("sin ningun cambio, dice que no hubo cambios y no hay advertencia", () => {
    expect(resumirDiffEsquema(diff({}))).toEqual({ resumen: "Sin cambios de esquema.", advertencia: null });
  });

  it("junta columnas nuevas, perdidas, con tipo cambiado y el delta de filas", () => {
    const { resumen } = resumirDiffEsquema(
      diff({
        columnas_nuevas: ["sucursal"],
        columnas_perdidas: ["descuento"],
        columnas_tipo_cambiado: [{ nombre: "id_venta", tipo_anterior: "texto", tipo_nuevo: "entero" }],
        filas_antes: 100,
        filas_despues: 150,
      }),
    );
    expect(resumen).toContain("+sucursal");
    expect(resumen).toContain("−descuento");
    expect(resumen).toContain("id_venta (texto→entero)");
    expect(resumen).toContain("+50 filas");
  });

  it("una columna perdida que el modelo usa genera una advertencia aparte", () => {
    const { advertencia } = resumirDiffEsquema(diff({ columnas_perdidas: ["importe"], columnas_perdidas_en_uso: ["importe"] }));
    expect(advertencia).toContain("importe");
    expect(advertencia).toContain("está");
  });

  it("una columna perdida que NADIE usa no genera advertencia", () => {
    const { advertencia } = resumirDiffEsquema(diff({ columnas_perdidas: ["descuento"] }));
    expect(advertencia).toBeNull();
  });

  it("plural cuando se pierde mas de una columna en uso", () => {
    const { advertencia } = resumirDiffEsquema(diff({ columnas_perdidas: ["importe", "fecha"], columnas_perdidas_en_uso: ["importe", "fecha"] }));
    expect(advertencia).toContain("están");
  });
});
