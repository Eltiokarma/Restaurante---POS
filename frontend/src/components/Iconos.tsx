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
