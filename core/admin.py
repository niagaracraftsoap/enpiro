from django.contrib import admin

from .models import Symbol, Term, TermSymbol


admin.site.register((Symbol, Term, TermSymbol))
