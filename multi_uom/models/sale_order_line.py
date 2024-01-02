# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare, float_round
from odoo.exceptions import ValidationError



class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    uom_quantity = fields.Float('Uom qty')
    multi_uom_ids = fields.Many2many('uom.uom', compute='change_product_for_uom')
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure', domain="[('id', 'in', multi_uom_ids)]")

    @api.depends('product_id')
    def change_product_for_uom(self):
        for val in self:
            list_uom = []
            if val.product_id:
                stock = self.env['stock.quant'].search(
                    [('product_id', '=', val.product_id.id), ('location_id.usage', '=', 'internal')])
                list_uom += stock.product_uom_id.ids
            else:
                list_uom = False
            if list_uom:
                list_uom = self.env['uom.uom'].search([('id', 'in', list_uom)])
            val.multi_uom_ids = list_uom

    @api.onchange("product_id", "product_uom", 'product_uom_qty')
    # The last parameter on the search function will only work if the location on the sales order line represents the stock location    for the warehouse on the sales order, the search function will not work if we have multiple step route.  
    def get_uom_by_product_and_uom(self):
        for line in self:
            if line.product_id and line.product_uom:
                all_quants = self.env['stock.quant'].search([('product_id', '=', line.product_id.id),
                                                ('uom_id_2', '=', line.product_uom.id),
                                                        ('location_id.usage','=', 'internal')])
                total_qyt = 0
                for quant in all_quants:
                    total_qyt += quant.available_quantity
                line.uom_quantity = total_qyt
            else:
                line.uom_quantity = 0
    
    @api.constrains('uom_quantity')
    def _check_available_qunat(self):
        for record in self:
            if record.uom_quantity <= 0 or record.product_uom_qty > record.uom_quantity:
                raise ValidationError("The quantity you have set or the unit of measure doesn't exist on the warehouse ")
            
            
                
                
    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """
        Launch procurement group run method with required/custom fields genrated by a
        sale order line. procurement group will launch '_run_pull', '_run_buy' or '_run_manufacture'
        depending on the sale order line product rule.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        procurements = []
        for line in self:
            line = line.with_company(line.company_id)
            if line.state != 'sale' or not line.product_id.type in ('consu','product'):
                continue
            qty = line._get_qty_procurement(previous_product_uom_qty)
            if float_compare(qty, line.product_uom_qty, precision_digits=precision) >= 0:
                continue

            group_id = line._get_procurement_group()
            if not group_id:
                group_id = self.env['procurement.group'].create(line._prepare_procurement_group_vals())
                line.order_id.procurement_group_id = group_id
            else:
                # In case the procurement group is already created and the order was
                # cancelled, we need to update certain values of the group.
                updated_vals = {}
                if group_id.partner_id != line.order_id.partner_shipping_id:
                    updated_vals.update({'partner_id': line.order_id.partner_shipping_id.id})
                if group_id.move_type != line.order_id.picking_policy:
                    updated_vals.update({'move_type': line.order_id.picking_policy})
                if updated_vals:
                    group_id.write(updated_vals)

            values = line._prepare_procurement_values(group_id=group_id)
            product_qty = line.product_uom_qty - qty

            # line_uom = line.product_uom
            # quant_uom = line.product_id.uom_id
            # product_qty = product_qty
            procurement_uom = line.product_uom
            procurements.append(self.env['procurement.group'].Procurement(
                line.product_id, product_qty, procurement_uom,
                line.order_id.partner_shipping_id.property_stock_customer,
                line.name, line.order_id.name, line.order_id.company_id, values))
        if procurements:
            self.env['procurement.group'].run(procurements)
        # return True

        # res = super(SaleOrderLine, self)._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)
        orders = list(set(x.order_id for x in self))
        for order in orders:
            reassign = order.picking_ids.filtered(lambda x: x.state=='confirmed' or (x.state in ['waiting', 'assigned'] and not x.printed))
            if reassign:
                # Trigger the Scheduler for Pickings
                reassign.action_confirm()
                reassign.action_assign()
        return True
    
class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    @api.onchange('warehouse_id')
    def _onchange_check_available_qunat_in_so_line(self):
        # Trigger checking available quantity in warehouse 
        for line in self.order_line:
            line.get_uom_by_product_and_uom()

     
   
