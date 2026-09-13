import { describe, expect, it } from "vitest";

import { ladoDeSoltar } from "./arrastre";

const CAJA = { left: 100, top: 200, width: 40, height: 20 };

describe("ladoDeSoltar", () => {
  it("la esquina arriba-izquierda es 'antes'", () => {
    expect(ladoDeSoltar(101, 201, CAJA)).toBe("antes");
  });

  it("la esquina abajo-derecha es 'despues'", () => {
    expect(ladoDeSoltar(139, 219, CAJA)).toBe("despues");
  });

  it("el punto exacto del centro geometrico es 'antes' (empate a favor de antes)", () => {
    expect(ladoDeSoltar(CAJA.left + CAJA.width / 2, CAJA.top + CAJA.height / 2, CAJA)).toBe("antes");
  });

  it("mitad izquierda a media altura es 'antes', aunque este mas abajo que el centro vertical", () => {
    expect(ladoDeSoltar(CAJA.left + 2, CAJA.top + CAJA.height - 2, CAJA)).toBe("antes");
  });

  it("mitad derecha a media altura es 'despues'", () => {
    expect(ladoDeSoltar(CAJA.left + CAJA.width - 1, CAJA.top + 1, CAJA)).toBe("despues");
  });

  it("con un rectangulo sin tamaño (no deberia pasar, pero no rompe) devuelve 'antes'", () => {
    expect(ladoDeSoltar(0, 0, { left: 0, top: 0, width: 0, height: 0 })).toBe("antes");
  });
});
