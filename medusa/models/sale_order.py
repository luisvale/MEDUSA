from odoo import models, fields, api, _

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    validated_invoice_id = fields.Many2one(
        'account.invoice', 
        string='Validado por la Factura', 
        help='Es la factura que valido este picking.'
    )

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
                        picking.sudo().action_done()

                        # Registrar que los movimientos de inventario se validaron
                        invoice.message_post(body=_("Los movimientos de inventario relacionados al pedido %s han sido confirmados y procesados según la factura.") % sale_order.name)

        return res

class AccountInvoiceRefund(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_open(self):
        # Llama al método original para validar la nota de crédito
        res = super(AccountInvoiceRefund, self).action_invoice_open()

        for invoice in self:
            if invoice.type == 'out_refund' and invoice.origin:
                # Buscar la factura original asociada a la nota de crédito
                original_invoice = self.env['account.invoice'].search([('number', '=', invoice.origin)], limit=1)
                if original_invoice and original_invoice.sale_order_id:
                    # Obtener el pedido de ventas asociado a la factura original
                    sale_order = original_invoice.sale_order_id
                    if sale_order:
                        for line in invoice.invoice_line_ids:
                            product = line.product_id
                            if product.type != 'service':
                                # Crear movimiento de devolución por los productos devueltos
                                related_picking = sale_order.picking_ids.filtered(lambda p: p.state == 'done')
                                if related_picking:
                                    return_wizard = self.env['stock.return.picking'].create({'picking_id': related_picking.id})
                                    return_wizard.product_return_moves.filtered(lambda r: r.product_id == product).update({
                                        'quantity': line.quantity,
                                        'to_refund': True
                                    })
                                    return_wizard.create_returns()
                                    # Registrar la acción en el chatter
                                    invoice.message_post(body=_("Se ha creado una devolución para el producto %s asociado a la nota de crédito.") % product.display_name)
        return res

    def _create_return_picking(self, picking, invoice):
        # Wizard de devolución para crear un nuevo picking de retorno
        return_wizard = self.env['stock.return.picking'].create({'picking_id': picking.id})
        return_wizard.product_return_moves.write({'to_refund': True})
        return_picking, _ = return_wizard.create_returns()
        return_picking.action_done()
        # Registrar la acción en el chatter de la factura
        invoice.message_post(body=_("Return picking %s created and processed due to this credit note.") % return_picking.name)