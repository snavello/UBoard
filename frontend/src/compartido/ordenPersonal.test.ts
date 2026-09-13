import { describe, expect, it } from "vitest";

import { combinarOrden, moverEnOrden } from "./ordenPersonal";

describe("combinarOrden", () => {
  it("respeta el orden guardado cuando los ids no cambiaron", () => {
    expect(combinarOrden(["c", "a", "b"], ["a", "b", "c"])).toEqual(["c", "a", "b"]);
  });

  it("agrega al final los ids nuevos que no estaban guardados", () => {
    expect(combinarOrden(["b", "a"], ["a", "b", "c"])).toEqual(["b", "a", "c"]);
  });

  it("ignora los ids guardados que ya no existen", () => {
    expect(combinarOrden(["z", "a", "b"], ["a", "b"])).toEqual(["a", "b"]);
  });

  it("sin nada guardado, devuelve los ids actuales tal cual", () => {
    expect(combinarOrden([], ["a", "b", "c"])).toEqual(["a", "b", "c"]);
  });
});

describe("moverEnOrden", () => {
  it("mueve un elemento justo antes de otro, mas adelante en la lista", () => {
    expect(moverEnOrden(["a", "b", "c", "d"], "a", "c")).toEqual(["b", "a", "c", "d"]);
  });

  it("mueve un elemento justo antes de otro, mas atras en la lista", () => {
    expect(moverEnOrden(["a", "b", "c", "d"], "d", "b")).toEqual(["a", "d", "b", "c"]);
  });

  it("mover el primero al final (arrastrarlo mas alla del ultimo) lo deja justo antes del ultimo", () => {
    // "mover antes de X" no tiene un "al final" explicito: para eso hay que
    // soltarlo sobre el ultimo elemento, que lo deja inmediatamente antes.
    expect(moverEnOrden(["a", "b", "c"], "a", "c")).toEqual(["b", "a", "c"]);
  });

  it("no hace nada si el origen y el destino son el mismo", () => {
    const orden = ["a", "b", "c"];
    expect(moverEnOrden(orden, "b", "b")).toBe(orden);
  });

  it("no hace nada si el origen no esta en la lista", () => {
    const orden = ["a", "b", "c"];
    expect(moverEnOrden(orden, "x", "b")).toBe(orden);
  });

  it("no hace nada si el destino no esta en la lista", () => {
    const orden = ["a", "b", "c"];
    expect(moverEnOrden(orden, "a", "x")).toBe(orden);
  });
});
