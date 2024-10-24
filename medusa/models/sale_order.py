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
                for picking in invoice.sale_order_id.picking_ids:
                    if picking.state in ['confirmed', 'assigned']:
                        for move_line in picking.move_line_ids:
                            invoice_line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == move_line.product_id)
                            if invoice_line:
                                qty_to_process = sum(line.quantity for line in invoice_line)
                                move_line.qty_done = min(qty_to_process, move_line.product_uom_qty)
                                if move_line.qty_done == move_line.product_uom_qty:
                                    move_line.move_id._action_done()
                        picking.validated_invoice_id = invoice
                        picking.sudo().action_done()
                        invoice.message_post(body=_("Los movimientos de inventario relacionados al pedido %s han sido confirmados y procesados según la factura.") % invoice.sale_order_id.name)
        return res

class AccountInvoiceRefund(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoiceRefund, self).action_invoice_open()
        for invoice in self:
            if invoice.type == 'out_refund' and invoice.origin:
                original_invoice = self.env['account.invoice'].search([('number', '=', invoice.origin)], limit=1)
                if original_invoice and original_invoice.validated_invoice_id:
                    for picking in original_invoice.sale_order_id.picking_ids.filtered(lambda p: p.validated_invoice_id == original_invoice):
                        return_wizard = self.env['stock.return.picking'].create({'picking_id': picking.id})
                        return_wizard.product_return_moves.write({'to_refund': True})
                        return_picking, _ = return_wizard.create_returns()
                        return_picking.action_done()
                        invoice.message_post(body=_("Return picking %s created and processed due to this credit note.") % return_picking.name)
        return res