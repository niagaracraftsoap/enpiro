from django.contrib import admin

from .models import RootKey, Symbol, SystemKey, Term, TermSymbol


admin.site.register((RootKey, SystemKey, Symbol, Term, TermSymbol))
