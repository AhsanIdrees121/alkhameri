# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class multi_uom(models.Model):
#     _name = 'multi_uom.multi_uom'
#     _description = 'multi_uom.multi_uom'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
