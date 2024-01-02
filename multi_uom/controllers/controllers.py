# -*- coding: utf-8 -*-
# from odoo import http


# class MultiUom(http.Controller):
#     @http.route('/multi_uom/multi_uom/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/multi_uom/multi_uom/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('multi_uom.listing', {
#             'root': '/multi_uom/multi_uom',
#             'objects': http.request.env['multi_uom.multi_uom'].search([]),
#         })

#     @http.route('/multi_uom/multi_uom/objects/<model("multi_uom.multi_uom"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('multi_uom.object', {
#             'object': obj
#         })
