# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class manage_uom_stock_qty(models.Model):
#     _name = 'manage_uom_stock_qty.manage_uom_stock_qty'
#     _description = 'manage_uom_stock_qty.manage_uom_stock_qty'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
# 1) Detail operation.
# 2) On 0 lot qty not update.
# 3) Issue of security for stock on hand.
# 4) hiding sale order button.
# 5) Reservation testing.