/**
 * Iconos SVG inline (§4): unifican el lenguaje icónico que antes eran
 * emoji (🍳 💵 🪑 ⏱ ⚙). Dibujados a mano sobre una grilla de 24×24,
 * trazos de 2px y color `currentColor`: heredan el color del texto y se
 * ven idénticos en cualquier tablet, con o sin internet.
 */
interface Props {
  tam?: number
  className?: string
}

function base(tam: number) {
  return {
    width: tam,
    height: tam,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    style: { verticalAlign: '-0.15em' },
  }
}

/** 🍳 Sartén de la cocina */
export function IconoSarten({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <circle cx="10" cy="12" r="7" />
      <circle cx="10" cy="12" r="2.6" fill="currentColor" stroke="none" />
      <path d="M17 12h5" />
    </svg>
  )
}

/** 💵 Billete de la caja */
export function IconoBillete({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <rect x="2" y="6" width="20" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.8" />
      <path d="M5.5 9.5v.01M18.5 14.5v.01" />
    </svg>
  )
}

/** 🪑 Silla de las mesas */
export function IconoSilla({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <path d="M7 3v8m0 0h10M7 11v10m10-10V3m0 8v10M7 15h10" />
    </svg>
  )
}

/** ⏱ Reloj de los temporizadores */
export function IconoReloj({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <circle cx="12" cy="13" r="8" />
      <path d="M12 9v4l2.8 2M9.5 2.5h5" />
    </svg>
  )
}

/** ⚙ Engranaje del admin */
export function IconoEngranaje({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1" />
    </svg>
  )
}

/** 🚫 Prohibido: cintillo de orden anulada en cocina */
export function IconoProhibido({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M5.8 5.8l12.4 12.4" />
    </svg>
  )
}

/** 🔓 Candado abierto: abrir / reabrir la caja */
export function IconoCandadoAbierto({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
      <path d="M8 10.5V7a4 4 0 0 1 7.6-1.7" />
      <path d="M12 14.5v2.5" />
    </svg>
  )
}

/** 🔒 Candado cerrado: cerrar la caja */
export function IconoCandadoCerrado({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
      <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" />
      <path d="M12 14.5v2.5" />
    </svg>
  )
}

/** 💸 Egreso: plata que sale del cajón */
export function IconoEgreso({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <rect x="2.5" y="8" width="15" height="10" rx="2" />
      <circle cx="10" cy="13" r="2.4" />
      <path d="M18.5 8.5l3 3m0 0l-3 3m3-3h-6" />
    </svg>
  )
}

/** 💳 Tarjeta de pago */
export function IconoTarjeta({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <rect x="2.5" y="5.5" width="19" height="13" rx="2" />
      <path d="M2.5 10h19M6 14.5h4" />
    </svg>
  )
}

/** 📱 Celular: Yape / billeteras móviles */
export function IconoMovil({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <rect x="7" y="2.5" width="10" height="19" rx="2.5" />
      <path d="M11 18.5h2" />
    </svg>
  )
}

/** 🖨️ Impresora: reimprimir tickets */
export function IconoImpresora({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <path d="M7 8V3.5h10V8" />
      <rect x="3.5" y="8" width="17" height="8.5" rx="1.5" />
      <path d="M7 13.5h10v7H7z" />
      <path d="M17 10.8h.01" />
    </svg>
  )
}

/** ✏️ Lápiz: corregir un dato */
export function IconoLapiz({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <path d="M4 20l1-4.5L16.5 4a2.1 2.1 0 0 1 3 0l.5.5a2.1 2.1 0 0 1 0 3L8.5 19z" />
      <path d="M14.5 6l3.5 3.5" />
    </svg>
  )
}

/** ✖ Aspa: anular / borrar */
export function IconoAspa({ tam = 24, className }: Props) {
  return (
    <svg {...base(tam)} className={className}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}
