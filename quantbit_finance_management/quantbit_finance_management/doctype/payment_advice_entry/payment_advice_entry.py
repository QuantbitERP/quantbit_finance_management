# Copyright (c) 2024, Quantbit Technologies Pvt. Lti. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_details

def getval(value):
	return value if value else 0

class PaymentAdviceEntry(Document):
    
    
	def before_save(self):
		self.calculate_total_fields()
		self.check_outstanding_allotment()
  
	@frappe.whitelist()
	def calculate_total_fields(self):
		self.grand_total = self.calculate_total(child_table="payment_advice_details",total_field="grand_total",condition_field= "check")
		self.total_allocated = self.calculate_total(child_table="payment_advice_details",total_field="allocated_amount",condition_field= "check")
		self.total_paidreceipt = self.calculate_total(child_table="payment_advice_details",total_field="paidreceipt_amount",condition_field= "check")
		self.total_discount = self.calculate_total(child_table="payment_advice_details",total_field="discount_amount",condition_field= "check")
		self.total_deduction = self.calculate_total(child_table="payment_advice_details",total_field="deduction_amount",condition_field= "check")

	@frappe.whitelist()
	def check_outstanding_allotment(self):
		for i in self.get("payment_advice_details",{"check":1}):
			if(i.allocated_amount > i.outstanding_amount):
				frappe.msgprint(f'Row {i.idx}: Allocated Amount cannot be greater than outstanding amount.', "Warning")

	@frappe.whitelist()
	def get_payment_references(self):
		party = self.party
		party_type = self.party_type
		self.get_party_name()

		doctype_mappings = {
			"Sales Invoice": {
				"party_field": "customer",
				"fields": ['name', 'grand_total', 'outstanding_amount', "return_against", "base_net_total", "net_total"],
			},
			"Purchase Invoice": {
				"party_field": "supplier",
				"fields": ['name', 'grand_total', 'outstanding_amount', "return_against", "taxes_and_charges_deducted", 
						"total", 'bill_no', 'bill_date'],
			},
		}
		updated_doc = []

		# Process Sales and Purchase Invoices
		for doctype, config in doctype_mappings.items():
			docs = frappe.get_all(
				doctype,
				filters={config["party_field"]: party, "docstatus": 1},
				fields=config["fields"]
			)

			for entry in docs:
				if round(entry.get("outstanding_amount", 0), 2) != 0.00:
					entry["doctype"] = doctype
					entry["ref_doctype"] = entry.get("return_against")
					entry["base_net_total"] = entry.get("base_net_total") if doctype == "Sales Invoice" else None
					entry["total"] = (
						entry.get("total") if doctype == "Purchase Invoice" else entry.get("net_total")
					)
					entry["taxes_and_charges_deducted"] = entry.get("taxes_and_charges_deducted") if doctype == "Purchase Invoice" else None
					entry["bill_no"] = entry.get("bill_no") if doctype == "Purchase Invoice" else None
					entry["bill_date"] = entry.get("bill_date") if doctype == "Purchase Invoice" else None
					updated_doc.append(entry)

		# Process Journal Entries
		journal_entries = frappe.db.sql(
			"""
			SELECT jea.parent, jea.debit_in_account_currency, jea.credit_in_account_currency, 
				jea.reference_name, jea.account
			FROM `tabJournal Entry Account` jea
			JOIN `tabJournal Entry` je ON je.name = jea.parent
			WHERE je.is_system_generated = 0
			AND jea.party = %s
			AND jea.party_type = %s
			AND jea.docstatus = 1
			""",
			(party, party_type),
			as_dict=True
		)

		for entry in journal_entries:
			outstanding_amt = self.calculate_outstanding_amount(entry["account"], 
														entry["debit_in_account_currency"], 
														entry["credit_in_account_currency"])

			entry.update({
				"doctype": "Journal Entry",
				"name": entry["parent"],
				"grand_total": entry["credit_in_account_currency"] or entry["debit_in_account_currency"],
				"outstanding_amount": round(outstanding_amt, 2),
				"ref_doctype": None,
				"base_net_total": None,
				"total": None,
				"taxes_and_charges_deducted": None,
				"bill_no": None,
				"bill_date": None,
			})
			updated_doc.append(entry)

		# return updated_doc
		for i in updated_doc:
			self.append("payment_advice_details",{
				"reference_id":i.name,
				"outstanding_amount":round(i.outstanding_amount,2),
				"grand_total":i.grand_total,
				"type":i.doctype,
				"reference_document":i.ref_doctype,
				"supplier_invoice_no":i.bill_no if i.type=="Purchase Invoice" else 0,
				"supplier_invoice_date":i.bill_date if i.type=="Purchase Invoice" else 0,
				"total":i.grand_total if i.type=="Journal Entry" else i.total,
				"tds_apply_amount":i.base_net_total if i.base_net_total else 0,
				"pi_discount_apply_amount":i.taxes_and_charges_deducted if i.taxes_and_charges_deducted else 0,
			})

	@frappe.whitelist()
	def calculate_outstanding_amount(account, debit, credit):
		"""
		Calculate outstanding amount based on account type and values.
		"""
		account_type = frappe.get_value("Account", {"name": account}, "account_type")
		if credit:
			return -credit if account_type == "Receivable" else credit
		if debit:
			return -debit if account_type == "Payable" else debit
		return 0


	def calculate_allocate_paid_amount(self,deduction_amount, discount_amount, outstanding_amount):
		paidreceipt_amount = round((outstanding_amount - (discount_amount + deduction_amount)), 2)
		allocated_amount = round((paidreceipt_amount + discount_amount + deduction_amount), 2)
		return paidreceipt_amount, allocated_amount

	def calculate_total(self, child_table, total_field,condition_field):
		return sum(getattr(i, total_field) for i in self.get(child_table, {condition_field:['not in', [None , 0]]}))

	def calculate_discount_and_deduction(self,discount_rate,deduction_rate,grand_total,total):
		discount_amount = round(getval(discount_rate)* getval(grand_total)/100 , 2)
		deduction_amount = round(getval(deduction_rate)* getval(total)/100 , 2)
		return discount_amount , deduction_amount


	def calculate_if_pi_discount(self,discount_rate,total,deduction_amount):
		discount_amount = round(getval(discount_rate)* getval(total)/100 , 2)
		paidreceipt_amount = round(getval(total) - (getval(discount_amount)+getval(deduction_amount)),2)
		allocated_amount = round(getval(paidreceipt_amount)+ getval(discount_amount)+getval(deduction_amount))
		return discount_amount , paidreceipt_amount , allocated_amount

	@frappe.whitelist()
	def get_party_name(self):
		party_doc = get_party_details(self.company,self.party_type,self.party,self.date,cost_center=None)
		self.party_name = party_doc.get("party_name")
 
	@frappe.whitelist()
	def calculation_on_discount_rate(self):
		total = 0
		for i in self.get("payment_advice_details",{"check":1}):
			total = i.grand_total+ i.pi_discount_apply_amount
			if i.grand_total > 0:
				if i.pi_discount_apply_amount > 0:
					i.deduction_amount  = round(getval(self.deduction_rate) * (i.total) / 100, 2)
					i.discount_amount,i.paidreceipt_amount,i.allocated_amount = self.calculate_if_pi_discount(self.discount_rate,total,i.deduction_amount)
				else:
					i.discount_amount, i.deduction_amount = self.calculate_discount_and_deduction(self.discount_rate,self.deduction_rate,i.grand_total,i.total)
					i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)

			else:
				i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)
		self.calculate_total_fields()
    
    
    
	@frappe.whitelist()
	def calculation_on_deduction_rate(self):
		for i in self.get("payment_advice_details",{"check":1}):
			if i.tds_apply_amount > 0:
				i.deduction_amount = round((getval(self.deduction_rate) * (i.tds_apply_amount) / 100), 2)
				i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)
			else:
				i.deduction_amount  = round(getval(self.deduction_rate) * (i.total) / 100, 2)
				i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)
    	
		self.calculate_total_fields()
  
	@frappe.whitelist()
	def calculation_on_discount_on_base_total(self):
		for i in self.get("payment_advice_details",{"check":1}):
			if i.grand_total > 0 and self.discount_on_base_total:
				i.discount_amount, i.deduction_amount = self.calculate_discount_and_deduction(self.discount_rate,self.deduction_rate,i.grand_total,i.total)
				i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)
			else:
				i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)
  
		self.calculate_total_fields()
  
	@frappe.whitelist()
	def calculation_on_discount(self):
		total = 0
		for i in self.get("payment_advice_details",{"check":1}):
			total = i.grand_total+ i.pi_discount_apply_amount
			if i.pi_discount_apply_amount > 0:
				i.deduction_amount  = round(getval(self.deduction_rate) * (i.total) / 100, 2)
				i.discount_amount,i.paidreceipt_amount,i.allocated_amount = self.calculate_if_pi_discount(self.discount_rate,total,i.deduction_amount)
			else:
				i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)
		self.calculate_total_fields()

	@frappe.whitelist()
	def calculation_on_deduction(self):
		for i in self.get("payment_advice_details",{"check":1}):
			i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)
		self.calculate_total_fields()


	@frappe.whitelist()
	def calculation_on_check(self):
		total = 0
		for i in self.get("payment_advice_details", {"allow_edit": 0}):
			if i.check:
				i.allow_edit = i.check
				total = i.grand_total + i.pi_discount_apply_amount

				if i.grand_total > 0:
					if i.pi_discount_apply_amount > 0:
						i.deduction_amount  = round(getval(self.deduction_rate) * (i.total) / 100, 2)
						i.discount_amount, i.paidreceipt_amount, i.allocated_amount = self.calculate_if_pi_discount(self.discount_rate, total, i.deduction_amount)
					elif i.tds_apply_amount > 0:
						i.discount_amount = round(getval(self.discount_rate) * (i.grand_total) / 100, 2)
						i.deduction_amount = round(getval(self.deduction_rate) * (i.tds_apply_amount) / 100, 2)
						i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)
					else:
						i.discount_amount, i.deduction_amount = self.calculate_discount_and_deduction(self.discount_rate, self.deduction_rate, i.grand_total, i.total)
						i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)
				else:
					i.paidreceipt_amount, i.allocated_amount = self.calculate_allocate_paid_amount(i.deduction_amount, i.discount_amount, i.outstanding_amount)

		self.calculate_total_fields()