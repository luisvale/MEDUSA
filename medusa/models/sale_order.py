#from odoo import api, fields, models, exceptions, _
#from odoo.exceptions import ValidationError, UserError
#from odoo.tools import float_is_zero, float_compare
#
#class SaleOrder(models.Model):
#    _inherit = "sale.order"
#
#    @api.multi
#    def action_confirm(self):
#        imediate_obj=self.env['stock.immediate.transfer']
#        res=super(SaleOrder,self).action_confirm()
#        for order in self:
#
#            warehouse=order.warehouse_id
#            if warehouse.is_delivery_set_to_done and order.picking_ids: 
#                for picking in self.picking_ids:
#                    picking.sudo().action_confirm()
#                    picking.sudo().action_assign()
#
#
#                    imediate_rec = imediate_obj.sudo().create({'pick_ids': [(4, order.picking_ids.id)]})
#                    imediate_rec.process()
#                    if picking.state !='done':
#                        for move in picking.move_ids_without_package:
#                            move.quantity_done = move.product_uom_qty
#                        picking.sudo().button_validate()
#
#            self._cr.commit()
#
#            if warehouse.create_invoice and not order.invoice_ids:
#                order.sudo().action_invoice_create()
#
#            if warehouse.validate_invoice and order.invoice_ids:
#                for invoice in order.invoice_ids:
#                    invoice.sudo().action_invoice_open()
#
#        return res
#
#    @api.multi
#    def _prepare_invoice(self):
#        """
#        Prepare the dict of values to create the new invoice for a sales order. This method may be
#        overridden to implement custom invoice generation (making sure to call super() to establish
 #       a clean extension chain).
#        """
#        self.ensure_one()
#        company_id = self.company_id.id
#        journal_id = (self.env['account.invoice'].with_context(company_id=company_id or self.env.user.company_id.id)
#            .default_get(['journal_id'])['journal_id'])
#        if not journal_id:
#            raise UserError(_('Please define an accounting sales journal for this company.'))
#
#        property_account_receivable_id = self.partner_invoice_id.property_account_receivable_id
#        if property_account_receivable_id.company_id != company_id:
#            account_id = self.env['account.account'].sudo().search([('code', '=', property_account_receivable_id.code), ('company_id', '=', company_id)])
#            if account_id:
#                property_account_receivable_id = account_id
#
#        return {
#            'name': (self.client_order_ref or '')[:2000],
#            'origin': self.name,
#            'type': 'out_invoice',
#            'account_id': property_account_receivable_id.id,
#            'partner_shipping_id': self.partner_shipping_id.id,
#            'journal_id': journal_id,
#            'currency_id': self.pricelist_id.currency_id.id,
#            'comment': self.note,
#            'partner_id': self.partner_invoice_id.id,
#            'payment_term_id': self.payment_term_id.id,
#            'fiscal_position_id': self.fiscal_position_id.id or self.partner_invoice_id.property_account_position_id.id,
#            'company_id': company_id,
#            'user_id': self.user_id and self.user_id.id,
#            'team_id': self.team_id.id,
#            'transaction_ids': [(6, 0, self.transaction_ids.ids)],
#            'payment_methods_id': self.payment_method_id.id or self.partner_id.payment_methods_id.id
#        }
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