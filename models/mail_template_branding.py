# -*- coding: utf-8 -*-
"""Branding SOM en los correos de venta.

Los templates nativos son noupdate: un <record> que los sobrescriba se
SALTA en el -u. Por eso los cuerpos viven como archivos HTML del módulo
y este helper los ESCRIBE en cada actualización vía <function>.
"""
import logging

from odoo import api, models
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

_TEMPLATES = {
    'sale.mail_template_sale_confirmation': {
        'file': 'sale_stone_selection/data/mail_bodies/confirmation.html',
        'subject': (
            'Your order {{ object.name or \'n/a\' }} is confirmed — '
            '(SOM)'),
    },
    'sale.email_template_edi_sale': {
        'file': 'sale_stone_selection/data/mail_bodies/quotation.html',
        'subject': (
            "Your {{ object.state in ('draft', 'sent') and 'quotation' "
            "or 'order' }} {{ object.name or 'n/a' }} — "
            '(SOM)'),
    },
}


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    @api.model
    def _som_apply_sale_mail_branding(self):
        for xmlid, spec in _TEMPLATES.items():
            template = self.env.ref(xmlid, raise_if_not_found=False)
            if not template:
                _logger.warning('[SOM MAIL] Template %s no existe.', xmlid)
                continue
            try:
                with file_open(spec['file'], 'r') as f:
                    body = f.read()
            except Exception:
                _logger.exception('[SOM MAIL] Sin cuerpo para %s.', xmlid)
                continue
            template.sudo().write({
                'subject': spec['subject'],
                'body_html': body,
            })
            _logger.info('[SOM MAIL] Branding aplicado a %s.', xmlid)
        return True
