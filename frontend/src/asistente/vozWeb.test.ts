import { describe, expect, it } from "vitest";

import { transcriptoDe, type EventoResultadoVoz } from "./vozWeb";

function evento(...transcripciones: string[]): EventoResultadoVoz {
  return { results: transcripciones.map((transcript) => [{ transcript }]) } as unknown as EventoResultadoVoz;
}

// obtenerConstructorDeVoz no se prueba aca: lee `window`, y estos tests
// corren en Node sin DOM (como formato.test.ts). Se verificó a mano en el
// navegador (ver docs/fase3-aceptacion.md, "Dictado por voz").
describe("transcriptoDe", () => {
  it("concatena un solo resultado", () => {
    expect(transcriptoDe(evento("cuánto vendió Pérez en marzo"))).toBe("cuánto vendió Pérez en marzo");
  });
  it("concatena resultados parciales y finales en orden", () => {
    expect(transcriptoDe(evento("agregá un ", "gráfico de ventas por sucursal"))).toBe("agregá un gráfico de ventas por sucursal");
  });
  it("sin resultados da texto vacío", () => {
    expect(transcriptoDe(evento())).toBe("");
  });
});
