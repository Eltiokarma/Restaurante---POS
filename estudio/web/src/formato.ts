export const soles = (n: number, dec = 0) =>
  `${n < 0 ? '−' : ''}S/ ${Math.abs(n).toLocaleString('es-PE', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })}`

export const miles = (n: number) => {
  const a = Math.abs(n)
  const signo = n < 0 ? '−' : ''
  if (a >= 1e6) return `${signo}${(a / 1e6).toFixed(a >= 1e7 ? 0 : 1)} M`
  if (a >= 1000) return `${signo}${(a / 1000).toFixed(a >= 10000 ? 0 : 1)} mil`
  return `${Math.round(n)}`
}

export const pct = (n: number, dec = 1) => `${(n * 100).toFixed(dec)} %`

export const anios = (n: number | null) =>
  n === null ? 'más de 10 años' : n < 1 ? `${Math.round(n * 12)} meses` : `${n.toFixed(1)} años`
