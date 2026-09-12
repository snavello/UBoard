/* Dictado por voz para el cuadro de preguntas (pedido de Sd durante la fase
   3): la Web Speech API del navegador, sin backend ni servicio externo.
   Anda en Chrome y Edge; Firefox y Safari en iOS no la tienen, ahi el boton
   de microfono directamente no se muestra (obtenerConstructorDeVoz devuelve
   null). TypeScript no trae tipos para esto, asi que se declara lo minimo
   que se usa. */

export interface EventoResultadoVoz extends Event {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}

export interface ReconocimientoVoz extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((evento: EventoResultadoVoz) => void) | null;
  onerror: ((evento: Event) => void) | null;
  onend: (() => void) | null;
}

type ConstructorReconocimientoVoz = new () => ReconocimientoVoz;

export function obtenerConstructorDeVoz(): ConstructorReconocimientoVoz | null {
  const ventana = window as unknown as {
    SpeechRecognition?: ConstructorReconocimientoVoz;
    webkitSpeechRecognition?: ConstructorReconocimientoVoz;
  };
  return ventana.SpeechRecognition ?? ventana.webkitSpeechRecognition ?? null;
}

/** Concatena todos los resultados (parciales incluidos) en un solo texto. */
export function transcriptoDe(evento: EventoResultadoVoz): string {
  let texto = "";
  for (let indice = 0; indice < evento.results.length; indice++) {
    texto += evento.results[indice][0].transcript;
  }
  return texto;
}
