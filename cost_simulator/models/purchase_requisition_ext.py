# -*- encoding: utf-8 -*-
##############################################################################
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see http://www.gnu.org/licenses/.
#
##############################################################################
from openerp.osv import orm
from openerp.tools.translate import _


class PurchaseRequisition(orm.Model):
    _inherit = 'purchase.requisition'

    def make_purchase_order_avanzosc(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        purchase_obj = self.pool['purchase.order']
        purchase_line_obj = self.pool['purchase.order.line']
        partner_obj = self.pool['res.partner']
        fiscal_position_obj = self.pool['account.fiscal.position']
        supplierinfo_obj = self.pool['product.supplierinfo']
        purchase_type_obj = self.pool['purchase.type']
        sequence_obj = self.pool['ir.sequence']
        res = {}
        for requisition in self.browse(cr, uid, ids, context=context):
            purchase_order_datas = []
            # Recorro todas las líneas de requisitos
            for line in requisition.line_ids:
                product = line.product_id
                # SELECCIONO TODOS LOS PROVEEDORES DEL PRODUCTO
                condition = [('product_id', '=', product.id)]
                supplierinfo_ids = supplierinfo_obj.search(cr, uid, condition,
                                                           context=context)
                if not supplierinfo_ids:
                    # Si no hay proveedores definidos para el producto, muestro
                    # el error
                    raise orm.except_orm(_('Purchase Order Creation Error'),
                                         _('You must define one supplier for '
                                           'the product: %s') % product.name)
                else:
                    for supplierinfo_id in supplierinfo_ids:
                        supplierinfo = supplierinfo_obj.browse(
                            cr, uid, supplierinfo_id, context=context)
                        supplier = partner_obj.browse(
                            cr, uid, supplierinfo.name.id, context=context)
                        # MIRO SI YA EXISTE UN PEDIDO DE COMPRA PARA EL
                        # PROVEEDOR QUE VIENE DEL PRODUCTO
                        condition = [('name', '=', 'Purchase')]
                        purchase_type_ids = purchase_type_obj.search(
                            cr, uid, condition, context=context)
                        if not purchase_type_ids:
                            raise orm.except_orm(_('Purchase Order Creation '
                                                   'Error'),
                                                 _('Purchase Type NOT FOUND'))
                        purchase_type = purchase_type_obj.browse(
                            cr, uid, purchase_type_ids[0], context=context)
                        condition = [('partner_id', '=', supplier.id),
                                     ('state', '=', 'draft'),
                                     ('requisition_id', '=', requisition.id),
                                     ('type', '=', purchase_type.id)]
                        purchase_order_id = purchase_obj.search(
                            cr, uid, condition, context=context)
                        if not purchase_order_id:
                            # SI NO EXISTE EL PEDIDO DE COMPRA PARA EL CLIENTE
                            delivery_address_id = partner_obj.address_get(
                                cr, uid, [supplier.id],
                                ['delivery'])['delivery']
                            pr = supplier.property_product_pricelist_purchase
                            loc = requisition.warehouse_id.lot_input_id
                            supplier_pricelist = pr or False
                            location_id = loc.id
                            code = purchase_type.sequence.code
                            seq = sequence_obj.get(cr, uid, code)
                            # Creo purchase order
                            fpos = (supplier.property_account_position and
                                    supplier.property_account_position.id or
                                    False)
                            warehouse = requisition.warehouse_id
                            vals = {'origin': requisition.name,
                                    'partner_id': supplier.id,
                                    'partner_address_id': delivery_address_id,
                                    'pricelist_id': supplier_pricelist.id,
                                    'location_id': location_id,
                                    'company_id': requisition.company_id.id,
                                    'fiscal_position': fpos,
                                    'requisition_id': requisition.id,
                                    'notes': requisition.description,
                                    'warehouse_id': warehouse.id,
                                    'type': purchase_type.id,
                                    'name': seq,
                                    }
                            purchase_id = purchase_obj.create(cr, uid, vals,
                                                              context=context)
                            purchase_order_datas.append(purchase_id)
                        else:
                            # SI EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR
                            # Cojo el ID del pedido de compra
                            purchase_id = purchase_order_id[0]

                        # DOY DE ALTA LA LINEA DEL PEDIDO DE COMPRA
                        delivery_address_id = partner_obj.address_get(
                            cr, uid, [supplier.id], ['delivery'])['delivery']
                        pr = (supplier.property_product_pricelist_purchase or
                              False)
                        supplier_pricelist = pr
                        seller_price, qty, default_uom_po_id, date_planned = (
                            self._seller_details(cr, uid, line, supplier,
                                                 context=context))
                        taxes_ids = product.supplier_taxes_id
                        taxes = fiscal_position_obj.map_tax(
                            cr, uid, supplier.property_account_position,
                            taxes_ids)
                        vals = {'order_id': purchase_id,
                                'name': product.partner_ref,
                                'product_qty': qty,
                                'product_id': product.id,
                                'product_uom': default_uom_po_id,
                                'price_unit': seller_price,
                                'date_planned': date_planned,
                                'notes': product.description_purchase,
                                'taxes_id': [(6, 0, taxes)],
                                }
                        purchase_line_obj.create(cr, uid, vals,
                                                 context=context)

            res[requisition.id] = purchase_order_datas
        return True

    def make_purchase_order(self, cr, uid, ids, partner_id, context=None):
        if context is None:
            context = {}
        assert partner_id, 'Supplier should be specified'
        purchase_obj = self.pool['purchase.order']
        purchase_line_obj = self.pool['purchase.order.line']
        partner_obj = self.pool['res.partner']
        purchase_type_obj = self.pool['purchase.type']
        fiscal_position_obj = self.pool['account.fiscal.position']
        sequence_obj = self.pool['ir.sequence']
        supplier = partner_obj.browse(cr, uid, partner_id, context=context)
        delivery_address_id = partner_obj.address_get(
            cr, uid, [supplier.id], ['delivery'])['delivery']
        supplier_pricelist = (supplier.property_product_pricelist_purchase or
                              False)
        res = {}
        for requisition in self.browse(cr, uid, ids, context=context):
            if supplier.id in filter(lambda x: x, [rfq.state != 'cancel' and
                                                   rfq.partner_id.id or None
                                                   for rfq in
                                                   requisition.purchase_ids]):
                raise orm.except_orm(_('Purchase Order Creation Error'),
                                     _('You have already one %s purchase order'
                                       ' for this partner, you must cancel '
                                       'this purchase order to create a new '
                                       'quotation.') % rfq.state)
            location_id = requisition.warehouse_id.lot_input_id.id
            condition = [('name', '=', 'Purchase')]
            purchase_type_ids = purchase_type_obj.search(cr, uid, condition,
                                                         context=context)
            if not purchase_type_ids:
                raise orm.except_orm(_('Purchase Order Creation Error'),
                                     _('Purchase Type NOT FOUND'))
            purchase_type = purchase_type_obj.browse(
                cr, uid, purchase_type_ids[0], context=context)
            code = purchase_type.sequence.code
            seq = sequence_obj.get(cr, uid, code)
            vals = {'origin': requisition.name,
                    'partner_id': supplier.id,
                    'partner_address_id': delivery_address_id,
                    'pricelist_id': supplier_pricelist.id,
                    'location_id': location_id,
                    'company_id': requisition.company_id.id,
                    'fiscal_position': (supplier.property_account_position and
                                        supplier.property_account_position.id
                                        or False),
                    'requisition_id': requisition.id,
                    'notes': requisition.description,
                    'warehouse_id': requisition.warehouse_id.id,
                    'type': purchase_type.id,
                    'name': seq,
                    }
            purchase_id = purchase_obj.create(cr, uid, vals, context=context)
            res[requisition.id] = purchase_id
            for line in requisition.line_ids:
                product = line.product_id
                seller_price, qty, default_uom_po_id, date_planned = (
                    self._seller_details(cr, uid, line, supplier,
                                         context=context))
                taxes_ids = product.supplier_taxes_id
                taxes = fiscal_position_obj.map_tax(
                    cr, uid, supplier.property_account_position, taxes_ids)
                purchase_line_obj.create(cr, uid, {
                    'order_id': purchase_id,
                    'name': product.partner_ref,
                    'product_qty': qty,
                    'product_id': product.id,
                    'product_uom': default_uom_po_id,
                    'price_unit': seller_price,
                    'date_planned': date_planned,
                    'notes': product.description_purchase,
                    'taxes_id': [(6, 0, taxes)],
                }, context=context)

        return res
