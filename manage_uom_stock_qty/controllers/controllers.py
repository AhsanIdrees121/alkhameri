# -*- coding: utf-8 -*-
# from odoo import http


# class ManageUomStockQty(http.Controller):
#     @http.route('/manage_uom_stock_qty/manage_uom_stock_qty/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/manage_uom_stock_qty/manage_uom_stock_qty/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('manage_uom_stock_qty.listing', {
#             'root': '/manage_uom_stock_qty/manage_uom_stock_qty',
#             'objects': http.request.env['manage_uom_stock_qty.manage_uom_stock_qty'].search([]),
#         })

#     @http.route('/manage_uom_stock_qty/manage_uom_stock_qty/objects/<model("manage_uom_stock_qty.manage_uom_stock_qty"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('manage_uom_stock_qty.object', {
#             'object': obj
#         })
