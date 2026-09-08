import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";

import { mensajeDeError } from "../compartido/api";
import { AvisoError } from "../compartido/componentes/Aviso";
import { rutaInicial, useSesion } from "../compartido/sesion";
import estilos from "./Ingresar.module.css";

export function Ingresar() {
  const { usuario, iniciar } = useSesion();
  const navegar = useNavigate();
  const [email, setEmail] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [enviando, setEnviando] = useState(false);

  if (usuario) return <Navigate to={rutaInicial(usuario)} replace />;

  const enviar = async (evento: FormEvent) => {
    evento.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      const quien = await iniciar(email, clave);
      navegar(rutaInicial(quien), { replace: true });
    } catch (fallo) {
      setError(fallo);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className={estilos.pagina}>
      <form className={estilos.tarjeta} onSubmit={enviar}>
        <span className="kicker">UBoard</span>
        <h1 className={estilos.titulo}>Tus datos, contados.</h1>
        <p className="secundario">Ingresá con el email y la clave que te dieron.</p>
        <label className="etiqueta">
          Email
          <input className="campo" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="etiqueta">
          Clave
          <input className="campo" type="password" autoComplete="current-password" required value={clave} onChange={(e) => setClave(e.target.value)} />
        </label>
        {error !== null && <AvisoError error={error} titulo={mensajeDeError(error) ? undefined : "No pudimos ingresar"} />}
        <button className="boton boton--primario" type="submit" disabled={enviando}>
          {enviando ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </div>
  );
}
