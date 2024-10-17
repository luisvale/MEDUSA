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

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.multi
    def action_confirm(self):
        stock_warnings = []
        
        for order in self:
            for picking in order.picking_ids:
                for move in picking.move_lines:  # En Odoo 12, se usa move_lines
                    if move.reserved_availability < move.product_uom_qty:
                        stock_warnings.append({
                            'product': move.product_id.name,
                            'needed_qty': move.product_uom_qty,
                            'available_qty': move.reserved_availability,
                        })

        if stock_warnings:
            message = "\n".join([
                _("Producto: %s | Cantidad requerida: %s | Cantidad disponible: %s") % (
                    warning['product'], warning['needed_qty'], warning['available_qty']
                )
                for warning in stock_warnings
            ])
            full_message = _(
                "Algunos productos no tienen suficiente disponibilidad para completar el pedido:\n\n%s\n\n"
                "Si confirma el pedido en este estado, no se podrá hacer la salida de inventario y la facturación no será posible. "
                "¿Desea continuar con la confirmación?"
            ) % message
            # Llama al wizard para advertir al usuario y permitir que continúe si lo desea
            return {
                'name': _('Stock insuficiente'),
                'type': 'ir.actions.act_window',
                'res_model': 'stock.warning.wizard',
                'view_mode': 'form',
                'view_type': 'form',
                'target': 'new',
                'context': {
                    'default_message': full_message,
                    'sale_order_id': self.id
                }
            }
        
        # Si no hay advertencias de stock, proceder con la confirmación del pedido
        return super(SaleOrder, self).action_confirm()

class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    sale_order_id = fields.Many2one(
        comodel_name="sale.order", 
        string="Pedido de Venta Relacionado",
        compute="_compute_sale_order_id",
        store=True
    )

    @api.depends('invoice_line_ids.sale_line_ids.order_id')
    def _compute_sale_order_id(self):
        for invoice in self:
            # Asocia el pedido de venta basado en las líneas de pedido
            sale_orders = invoice.invoice_line_ids.mapped('sale_line_ids.order_id')
            if sale_orders:
                invoice.sale_order_id = sale_orders[0]  # Asociar el primer pedido relacionado (si es múltiple)

    @api.multi
    def action_invoice_open(self):
        # Llama al método original para validar la factura
        res = super(AccountInvoice, self).action_invoice_open()

        for invoice in self:
            if invoice.sale_order_id:  # Usamos el campo relacionado al pedido de venta
                order = invoice.sale_order_id
                for picking in order.picking_ids:
                    if picking.state in ['confirmed', 'assigned', 'waiting']:
                        # Confirmar el picking si está en estado preparado o asignado
                        picking.sudo().action_confirm()
                        picking.sudo().action_assign()

                        partial_moves = []
                        pending_moves = []

                        # Procesar los movimientos de inventario relacionados
                        for move in picking.move_lines:  # En Odoo 12, move_ids_without_package es move_lines
                            if move.reserved_availability < move.product_uom_qty:
                                # Si no hay suficiente stock, hacer entrega parcial
                                partial_moves.append({
                                    'product': move.product_id.name,
                                    'needed_qty': move.product_uom_qty,
                                    'available_qty': move.reserved_availability,
                                })
                                move.quantity_done = move.reserved_availability
                            else:
                                move.quantity_done = move.product_uom_qty

                            # Si quedó pendiente parte del movimiento por falta de stock
                            if move.quantity_done < move.product_uom_qty:
                                pending_moves.append({
                                    'product': move.product_id.name,
                                    'pending_qty': move.product_uom_qty - move.quantity_done,
                                })

                        # Validar el picking para confirmar lo entregado
                        if picking.state not in ['done', 'cancel']:
                            picking.sudo().button_validate()

                        # Manejo de movimientos pendientes: Crear un nuevo movimiento para lo pendiente
                        if pending_moves:
                            picking_copy = picking.copy({
                                'move_lines': []
                            })
                            for move in picking.move_lines:
                                if move.quantity_done < move.product_uom_qty:
                                    remaining_qty = move.product_uom_qty - move.quantity_done
                                    move_copy = move.copy({
                                        'product_uom_qty': remaining_qty,
                                        'picking_id': picking_copy.id,
                                    })
                            picking_copy.action_confirm()

                        # Registrar el evento en el logger y en la factura
                        message = _("Factura %s: Entrega parcial realizada.\n") % invoice.number
                        if partial_moves:
                            partial_msg = "\n".join([
                                _("Producto: %s | Cantidad requerida: %s | Cantidad entregada: %s") % (
                                    move['product'], move['needed_qty'], move['available_qty']
                                ) for move in partial_moves
                            ])
                            message += _("Movimientos parciales:\n%s\n") % partial_msg
                        
                        if pending_moves:
                            pending_msg = "\n".join([
                                _("Producto: %s | Cantidad pendiente: %s") % (
                                    move['product'], move['pending_qty']
                                ) for move in pending_moves
                            ])
                            message += _("Movimientos pendientes registrados en un nuevo picking.\n%s\n") % pending_msg

                        _logger.info(message)
                        invoice.message_post(body=message)

        return res