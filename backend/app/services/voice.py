"""STUB — Pedido por voz (Fase 3).

Aquí se enchufa Whisper (transcripción) + Claude API (interpretación) en la
Fase 3. El contrato previsto es:

    interpretar_pedido(audio_o_texto, menu_de_hoy) -> list[{"plato_id", "cantidad"}]

La voz es solo OTRA MANERA de llenar el carrito: el resultado de este módulo
se agrega al carrito del frontend igual que un toque en pantalla. Todo lo
demás (resumen, confirmación, ventana de cancelación, ticket, cola de
cocina) es agnóstico a cómo se llenó el pedido y NO debe modificarse cuando
se implemente esta función.
"""


def interpretar_pedido(entrada, menu_de_hoy):
    """Sin implementar hasta la Fase 3."""
    raise NotImplementedError("Pedido por voz disponible en la Fase 3")
