pretty:
	perltidy `head -1 * | grep -B1 'perl' | grep -o '==>\s[^.]*\s' | sed -e 's/==>\s*//g'` -l 120 -ce -b
