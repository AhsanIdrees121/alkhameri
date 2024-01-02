# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools import float_compare, float_is_zero


# class InventoryLineInventoryLine(models.Model):
#     _inherit = "stock.inventory.line"
#     uom_id_2 = fields.Many2one('uom.uom', string='UOM 2', domain="[('category_id', '=', product_uom_category_id)]")
#     product_uom_category_id = fields.Many2one('uom.category', related='product_id.uom_id.category_id')
#
#     # @api.depends('uom_id_2')
#     # @api.onchange('uom_id_2')
#     # def onchange_uom_2(self):
#     #     for val in self:
#     #         if val.uom_id_2:
#     #             val.product_uom_id = val.uom_id_2
#
#
#     @api.model
#     def create(self, vals):
#         # TDE note: auto-subscription of manager done by hand, because currently
#         # the tracking allows to track+subscribe fields linked to a res.user record
#         # An update of the limited behavior should come, but not currently done.
#         if vals.get("uom_id_2") and vals.get("prod_lot_id"):
#             lot_id = self.env['stock.lot'].search([('id', '=', vals.get("prod_lot_id"))])
#             if lot_id:
#                 if lot_id.product_uom_id.id != vals.get("uom_id_2"):
#                     raise ValidationError('Your Lot/Serial Number UOM and UOM 2 should be same')
#
#         if vals.get("uom_id_2") and not vals.get("prod_lot_id"):
#             raise ValidationError(
#                 'Your Have to assign Lot/Serial Number')
#
#         if vals.get("uom_id_2"):
#             vals["product_uom_id"] = vals.get("uom_id_2")
#
#         return super(InventoryLineInventoryLine, self).create(vals)


# class Inventory(models.Model):
#     _inherit = "stock.inventory"
#
#     def _get_inventory_lines_values(self):
#         """Return the values of the inventory lines to create for this inventory.
#
#         :return: a list containing the `stock.inventory.line` values to create
#         :rtype: list
#         """
#         self.ensure_one()
#         quants_groups = self._get_quantities()
#         vals = []
#         for (product_id, location_id, lot_id, package_id, owner_id, uom_id), quantity in quants_groups.items():
#             line_values = {
#                 'inventory_id': self.id,
#                 'product_qty': 0 if self.prefill_counted_quantity == "zero" else quantity,
#                 'theoretical_qty': quantity,
#                 'prod_lot_id': lot_id,
#                 'partner_id': owner_id,
#                 'product_id': product_id,
#                 'location_id': location_id,
#                 'package_id': package_id,
#                 'product_uom_id': uom_id if uom_id else self.env['product.product'].browse(product_id).uom_id.id
#             }
#             vals.append(line_values)
#         if self.exhausted:
#             vals += self._get_exhausted_inventory_lines_vals({(l['product_id'], l['location_id']) for l in vals})
#         return vals
#
#     def _get_quantities(self):
#         """Return quantities group by product_id, location_id, lot_id, package_id and owner_id
#
#         :return: a dict with keys as tuple of group by and quantity as value
#         :rtype: dict
#         """
#         self.ensure_one()
#         if self.location_ids:
#             domain_loc = [('id', 'child_of', self.location_ids.ids)]
#         else:
#             domain_loc = [('company_id', '=', self.company_id.id), ('usage', 'in', ['internal', 'transit'])]
#         locations_ids = [l['id'] for l in self.env['stock.location'].search_read(domain_loc, ['id'])]
#
#         domain = [('company_id', '=', self.company_id.id),
#                   ('location_id', 'in', locations_ids)]
#         if self.prefill_counted_quantity == 'zero':
#             domain.append(('product_id.active', '=', True))
#
#         if self.product_ids:
#             domain = expression.AND([domain, [('product_id', 'in', self.product_ids.ids)]])
#
#         fields = ['product_id', 'location_id', 'lot_id', 'package_id', 'owner_id', 'uom_id_2', 'quantity:sum']
#         group_by = ['product_id', 'location_id', 'lot_id', 'package_id', 'owner_id', 'uom_id_2']
#
#         quants = self.env['stock.quant'].read_group(domain, fields, group_by, lazy=False)
#         return {(
#             quant['product_id'] and quant['product_id'][0] or False,
#             quant['location_id'] and quant['location_id'][0] or False,
#             quant['lot_id'] and quant['lot_id'][0] or False,
#             quant['package_id'] and quant['package_id'][0] or False,
#             quant['owner_id'] and quant['owner_id'][0] or False,
#             quant['uom_id_2'] and quant['uom_id_2'][0] or False
#                 ):
#             quant['quantity'] for quant in quants
#         }
