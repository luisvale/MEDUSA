from odoo import models, fields, api, _

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    validated_invoice_id = fields.Many2one(
        'account.invoice', 
        string='Validated by Invoice', 
        help='The invoice that validated this picking and set it to done.'
    )


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    # Campo Many2one que relaciona la factura con el picking que la validó
    validated_picking_id = fields.Many2one(
        'stock.picking', 
        string="Validated Picking", 
        readonly=True, 
        help="The picking that was validated by this invoice."
    )

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
        # Llama al método original para validar la factura
        res = super(AccountInvoice, self).action_invoice_open()

        for invoice in self:
            if invoice.sale_order_id:
                # Obtener los pickings relacionados al pedido de venta
                sale_order = invoice.sale_order_id
                for picking in sale_order.picking_ids:
                    if picking.state in ['confirmed', 'assigned']:
                        # Procesar cada picking relacionado
                        for move_line in picking.move_line_ids:
                            # Buscar la línea de factura correspondiente al producto del movimiento
                            invoice_line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == move_line.product_id)
                            if invoice_line:
                                qty_to_process = sum(line.quantity for line in invoice_line)
                                # Ajustar la cantidad hecha basada en la cantidad facturada
                                move_line.qty_done = qty_to_process if qty_to_process < move_line.product_uom_qty else move_line.product_uom_qty
                                # Validar el picking si la cantidad realizada es igual a la cantidad reservada
                                if move_line.qty_done == move_line.product_uom_qty:
                                    move_line.move_id._action_done()

                        # Validar el picking después de ajustar las cantidades y asignar la factura que lo validó
                        picking.validated_invoice_id = invoice
                        invoice.validated_picking_id = picking  # Relacionar la factura con el picking validado
                        picking.sudo().action_done()

                        # Registrar que los movimientos de inventario se validaron
                        invoice.message_post(body=_("Los movimientos de inventario relacionados al pedido %s han sido confirmados y procesados según la factura.") % sale_order.name)

        return res


class AccountInvoiceRefund(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_open(self):
        for invoice in self:
            if invoice.type == 'out_refund' and invoice.origin:
                # Buscar la factura original relacionada con la nota de crédito
                original_invoice = self.env['account.invoice'].search([('number', '=', invoice.origin)], limit=1)

                if original_invoice:
                    # Buscar el picking relacionado directamente a la factura original
                    picking = original_invoice.mapped('validated_picking_id')

                    if picking and picking.state == 'done':
                        # Si se encuentra un picking relacionado, abrir el wizard de devolución
                        return self._open_return_picking_wizard(picking)

                    else:
                        raise UserError(_("No se encontró un picking completado relacionado con la factura original."))
        # Continuar con la validación normal de la nota de crédito después del wizard
        return super(AccountInvoiceRefund, self).action_invoice_open()

    def _open_return_picking_wizard(self, picking):
        """Abrir el wizard de devolución para el picking asociado"""
        return_wizard = self.env['stock.return.picking'].create({'picking_id': picking.id})
        return_wizard._onchange_picking_id()  # Este método carga las líneas de productos automáticamente

        # Retornar la acción del wizard para mostrarlo al usuario
        return {
            'type': 'ir.actions.act_window',
            'name': 'Devolución de Picking',
            'res_model': 'stock.return.picking',
            'view_mode': 'form',
            'view_id': self.env.ref('stock.view_stock_return_picking_form').id,
            'target': 'new',
            'res_id': return_wizard.id,
            'context': self.env.context,
        }