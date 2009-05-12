class Uncomputed:
	"""
	A singleton to denote uncomputed values.
	"""
	pass

class lazy(object):
	"""
	Doubles up as a descriptor for lazy properties and a decorator for lazy functions.
	Example usage: 
	
	# === as a descriptor:
	class A(...):
		foo = lazy(lambda self: self._foo())
		def foo(self):
			...
	
	# example:
	a = A()
	print a.foo # computed
	print a.foo # looked up
	
	# === as a decorator:
	@lazy
	def foo():
		pass
	
	print foo() # computed
	print foo() # looked up
	"""	
	
	def __init__(self, thunk):
		self.thunk = thunk
		self.value = Uncomputed

	def __get__(self, instance, owner):
		if self.value == Uncomputed:
			self.value = self.thunk(instance)
		return self.value
	
	def __set__(self, instance, thunk):
		self.thunk = thunk
		self.value = Uncomputed
	
	def __delete__(self, instance):
		pass
	
	def __call__(self):
		if self.value == Uncomputed:
			self.value = self.thunk()
		return self.value

