# Copyright (c) 2024, Quantbit Technologies Pvt. Lti. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_details

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
		doctype_li = ["Sales Invoice","Purchase Invoice","Journal Entry"]
		updated_doc = []
		for doctype in doctype_li:
			if doctype != "Journal Entry":
				field_list=[]
				if doctype == "Sales Invoice":
					doctype_name ="customer" 
					field_list=['name','grand_total','outstanding_amount',"return_against","base_net_total","net_total"]
				else:
					doctype_name="Supplier"
					field_list=['name','grand_total','outstanding_amount',"return_against","taxes_and_charges_deducted","total" ,'bill_no','bill_date']
				doc = frappe.get_all(doctype, {doctype_name: party, 'docstatus': 1},field_list)
				if doc:
					for entry in doc:
						if round(entry.outstanding_amount,2) != 0.00:
							entry["doctype"] = doctype
							entry["ref_doctype"]=entry["return_against"] if entry["return_against"] else None
							if doctype =="Sales Invoice":
								entry["base_net_total"]=entry["base_net_total"] if entry["base_net_total"] else None
							else:
								entry["base_net_total"]=None
							if doctype =="Purchase Invoice":
								entry["total"]=entry["total"] if entry["total"] else None
							else:
								entry["total"]=entry["net_total"] if entry["net_total"] else None  
							
							if doctype =="Purchase Invoice":
								entry["taxes_and_charges_deducted"]=entry["taxes_and_charges_deducted"] if entry["taxes_and_charges_deducted"] else None
								entry["bill_no"]=entry["bill_no"] if entry["bill_no"] else None
								entry["bill_date"]=entry["bill_date"] if entry["bill_date"] else None
							else:
								entry["taxes_and_charges_deducted"]=None
								entry["bill_no"]=None
								entry["bill_date"]=None 
							updated_doc.append(entry)
			else:
				doc = frappe.db.sql("""
								SELECT jea.parent, jea.debit_in_account_currency, jea.credit_in_account_currency, 
									jea.reference_name, jea.account
								FROM `tabJournal Entry Account` jea
								JOIN `tabJournal Entry` je ON je.name = jea.parent
								WHERE je.is_system_generated = 0
								AND jea.party = %s
								AND jea.party_type = %s
								AND jea.docstatus = 1
							""", (party, party_type), as_dict=True)

				if doc:
					for entry in doc:
						outstanding_amt=0
						if(entry["credit_in_account_currency"]):
							account_doc=frappe.get_value("Account",{"name":entry["account"]},"account_type")
							outstanding_amt=-entry["credit_in_account_currency"] if(account_doc=="Receivable") else entry["credit_in_account_currency"]
						if(entry["debit_in_account_currency"]):
							account_doc=frappe.get_value("Account",{"name":entry["account"]},"account_type")
							outstanding_amt=-entry["debit_in_account_currency"] if(account_doc=="Payable") else entry["debit_in_account_currency"]
							
						entry["doctype"] = doctype
						entry["name"] = entry["parent"]
						entry["grand_total"] = entry["credit_in_account_currency"] or entry["debit_in_account_currency"]
						entry["outstanding_amount"] = round(outstanding_amt,2)
						entry["ref_doctype"]=  None
						entry["base_net_total"]=None
						entry["total"]=None  
						entry["taxes_and_charges_deducted"]=None
						entry["bill_no"]=None
						entry["bill_date"]=None 
						updated_doc.append(entry)
      
			
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

	def calculate_amounts_method(self,deduction_amount, discount_amount, outstanding_amount):
		paidreceipt_amount = round((outstanding_amount - (discount_amount + deduction_amount)), 2)
		allocated_amount = round((paidreceipt_amount + discount_amount + deduction_amount), 2)
		return paidreceipt_amount, allocated_amount

	def calculate_total(self, child_table, total_field,condition_field):
		return sum(getattr(i, total_field) for i in self.get(child_table, {condition_field:['not in', [None , 0]]}))


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
				if self.discount_on_base_total:
					i.discount_amount = round((self.discount_rate or 0) * (i.grand_total) / 100, 2)
					i.deduction_amount = round((self.deduction_rate or 0) * (i.total) / 100, 2)
					i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
				else:
					if i.pi_discount_apply_amount > 0:
						i.discount_amount = round(((self.discount_rate or 0) * (total) / 100), 2)
						i.paidreceipt_amount = round(total - (i.discount_amount + i.deduction_amount),2)
						i.allocated_amount = i.paidreceipt_amount + i.discount_amount + i.deduction_amount
					else:
						i.discount_amount = round((self.discount_rate or 0) * (i.grand_total) / 100, 2)
						i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
			else:
				i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
		self.calculate_total_fields()
    
    
	@frappe.whitelist()
	def calculation_on_deduction_rate(self):
		for i in self.get("payment_advice_details",{"check":1}):
			if i.tds_apply_amount > 0:
				i.deduction_amount = round(((self.deduction_rate or 0) * (i.tds_apply_amount) / 100), 2)
				i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
		self.calculate_total_fields()
  
	@frappe.whitelist()
	def calculation_on_discount_on_base_total(self):
		total = 0
		for i in self.get("payment_advice_details",{"check":1}):
			total = i.grand_total+ i.pi_discount_apply_amount
			if i.grand_total > 0:
				if self.discount_on_base_total:
					i.discount_amount = round((self.discount_rate or 0) * (i.grand_total) / 100, 2)
					i.deduction_amount = round((self.deduction_rate or 0) * (i.total) / 100, 2)
					i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
				else:
					if i.pi_discount_apply_amount > 0:
						i.discount_amount = round(((self.discount_rate or 0) * (total) / 100), 2)
						i.paidreceipt_amount = round(total - (i.discount_amount + i.deduction_amount),2)
						i.allocated_amount = i.paidreceipt_amount + i.discount_amount + i.deduction_amount
					else:
						i.discount_amount = round((self.discount_rate or 0) * (i.grand_total) / 100, 2)
						i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
  
			else:
				i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
  
		self.calculate_total_fields()
  
	@frappe.whitelist()
	def calculation_on_discount(self):
		total = 0
		for i in self.get("payment_advice_details",{"check":1}):
			total = i.grand_total+ i.pi_discount_apply_amount
			if self.discount_on_base_total:
				i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
			else:
				if i.pi_discount_apply_amount > 0:
					i.paidreceipt_amount = round(total - (i.discount_amount + i.deduction_amount),2)
					i.allocated_amount = i.paidreceipt_amount + i.discount_amount + i.deduction_amount
				else:
					i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
		self.calculate_total_fields()

	@frappe.whitelist()
	def calculation_on_deduction(self):
		for i in self.get("payment_advice_details",{"check":1}):
			i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
		self.calculate_total_fields()

	@frappe.whitelist()
	def calculation_on_check(self):
		# frappe.throw(str(type))
		total = 0
		for i in self.get("payment_advice_details",{"allow_edit":0}):
			if i.check:
				i.allow_edit = i.check
				total = i.grand_total+ i.pi_discount_apply_amount
				if self.discount_on_base_total and self.discount_rate and self.deduction_rate:
					i.discount_amount = round((self.discount_rate or 0) * (i.grand_total) / 100, 2)
					i.deduction_amount = round((self.deduction_rate or 0) * (i.total) / 100, 2)
					i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
				elif self.discount_on_base_total:
					i.deduction_amount = round((self.deduction_rate or 0) * (i.total) / 100, 2)
					i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
				elif self.discount_rate:
					if i.grand_total > 0:
						if self.discount_on_base_total:
							i.discount_amount = round((self.discount_rate or 0) * (i.grand_total) / 100, 2)
							i.deduction_amount = round((self.deduction_rate or 0) * (i.total) / 100, 2)
							i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
						else:
							if i.pi_discount_apply_amount > 0:
								i.discount_amount = round(((self.discount_rate or 0) * (total) / 100), 2)
								i.paidreceipt_amount = round(total - (i.discount_amount + i.deduction_amount),2)
								i.allocated_amount = i.paidreceipt_amount + i.discount_amount + i.deduction_amount
							else:
								i.discount_amount = round((self.discount_rate or 0) * (i.grand_total) / 100, 2)
								i.deduction_amount = round((self.deduction_rate or 0) * (i.total) / 100, 2)
								i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
					else:
						i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
      
				elif self.deduction_rate:
					if i.tds_apply_amount > 0:
						i.deduction_amount = round((self.deduction_rate or 0) * (i.tds_apply_amount) / 100, 2)
						i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
				else:
					if i.grand_total > 0:
						if self.discount_on_base_total:
							i.discount_amount = round((self.discount_rate or 0) * (i.grand_total) / 100, 2)
							i.deduction_amount = round((self.deduction_rate or 0) * (i.total) / 100, 2)
							i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
						else:
							if i.pi_discount_apply_amount > 0:
								i.discount_amount = round(((self.discount_rate or 0) * (total) / 100), 2)
								i.paidreceipt_amount = round(total - (i.discount_amount + i.deduction_amount),2)
								i.allocated_amount = i.paidreceipt_amount + i.discount_amount + i.deduction_amount
							else:
								i.discount_amount = round((self.discount_rate or 0) * (i.grand_total) / 100, 2)
								i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
					else:
							i.paidreceipt_amount, i.allocated_amount = self.calculate_amounts_method(i.deduction_amount, i.discount_amount, i.outstanding_amount)
       			
		self.calculate_total_fields()

   
  
  