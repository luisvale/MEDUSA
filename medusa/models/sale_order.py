from odoo import models, fields, api, _
from odoo.exceptions import UserError

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
    
    # Campo que relaciona la factura con el picking que la validó
    validated_picking_id = fields.Many2one(
        'stock.picking', 
        string='Validated Picking', 
        help='The picking that validated this invoice.'
    )

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
                        invoice.validated_picking_id = picking
                        invoice.message_post(body=_("Los movimientos de inventario relacionados al pedido %s han sido confirmados y procesados según la factura.") % sale_order.name)

        return res


class AccountInvoiceRefund(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoiceRefund, self).action_invoice_open()
        for invoice in self:
            if invoice.type == 'out_refund' and invoice.invoice_id:
                # Obtener la factura original desde invoice_id
                original_invoice = invoice.invoice_id

                # Verificar si la factura original tiene un picking relacionado
                if original_invoice and original_invoice.validated_picking_id:
                    picking = original_invoice.validated_picking_id

                    _logger.info(f"Picking relacionado encontrado: {picking.id} | Estado del picking: {picking.state}")

                    if picking and picking.state == 'done':
                        # Llamar al wizard de devolución del picking
                        return_wizard = self.env['stock.return.picking'].create({'picking_id': picking.id})

                        # Procesar la devolución
                        return_picking, _ = return_wizard.create_returns()

                        # Validar el picking de devolución
                        return_picking.action_done()

                        # Agregar un mensaje a la nota de crédito
                        invoice.message_post(body=_("Se ha creado y procesado la devolución de picking %s debido a esta nota de crédito.") % return_picking.name)
                    else:
                        raise UserError(_("No se encontró un picking en estado 'done' relacionado con la factura original."))
                else:
                    raise UserError(_("La factura original no tiene un picking asociado."))
        return res