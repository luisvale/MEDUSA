from odoo import models, fields, api

class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    # Campo Many2one que relaciona la factura con el pedido de venta
    sale_order_id = fields.Many2one('sale.order', string="Pedido de Venta Relacionado", readonly=True)

    @api.model
    def create(self, vals):
        # Crear la factura
        invoice = super(AccountInvoice, self).create(vals)
        
        # Relacionar el pedido de venta basado en el campo 'origin'
        if invoice.origin:
            sale_order = self.env['sale.order'].search([('name', '=', invoice.origin)], limit=1)
            if sale_order:
                invoice.sale_order_id = sale_order
        
        return invoice

    @api.multi
    def action_invoice_open(self):
        # Llamar al método original para validar la factura
        res = super(AccountInvoice, self).action_invoice_open()

        for invoice in self:
            if invoice.sale_order_id:
                # Obtener los pickings relacionados al pedido de venta
                sale_order = invoice.sale_order_id
                for picking in sale_order.picking_ids:
                    if picking.state not in ['done', 'cancel']:
                        picking.sudo().action_confirm()
                        picking.sudo().action_assign()

                        # Asignar automáticamente la cantidad hecha (qty_done)
                        for move_line in picking.move_line_ids:
                            move_line.qty_done = move_line.product_uom_qty  # Asignar la cantidad hecha igual a la reservada

                        # Validar el picking forzando la validación
                        picking.sudo().button_validate()

                # Registrar en la factura que los movimientos de inventario han sido validados
                invoice.message_post(body=_("Los movimientos de inventario relacionados al pedido %s han sido confirmados y procesados.") % sale_order.name)

        return res