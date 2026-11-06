import json
import os
import sqlite3
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk, filedialog, messagebox as mb

PAPKA = os.path.dirname(os.path.abspath(__file__))
BD, FD, OSNOVA, REZERV = os.path.join(PAPKA, 'komanda.db'), '%d.%m.%Y', 5, 2
POLYA = ('id', 'fio', 'razryad', 'do_formy', 'v_forme', 'pobedy')
ZAG = ('№', 'ФИО лыжника', 'Разряд', 'До пика формы, нед.', 'Сохранение формы, нед.', 'Победы')
RAZRYADY = ('МСМК', 'МС', 'КМС', 'I', 'II', 'III', 'б/р')  # от сильного к слабому
DATY = {'podgotovka': 'Начало подготовки', 'nachalo': 'Начало соревнования', 'konec': 'Конец соревнования'}
GRUPPY = ('весь период', 'частично', 'пик до старта', 'пик после финиша')
LEGENDA = (('основной', '#2e9d4f', 'основной состав'), ('резерв', '#f0a020', 'резерв'), ('', '#aaa', 'не в команде'))
CVET = {k: c for k, c, _ in LEGENDA}
TIPY = [('JSON', '*.json'), ('Все файлы', '*.*')]



def privesti(pole, v):
    """Значение из формы/JSON -> тип поля БД (пусто -> None)."""
    v = '' if v is None else str(v).strip()
    if not v or pole == 'fio':
        return v or None
    if pole == 'razryad':
        v = {'1': 'I', '2': 'II', '3': 'III'}.get(v, v)
        if v not in RAZRYADY:
            raise ValueError('Разряд - одно из: ' + ', '.join(RAZRYADY))
        return v
    if not v.isdigit():
        raise ValueError(ZAG[POLYA.index(pole)] + ': нужно целое число >= 0')
    return int(v)


def zapis(d):
    """Словарь -> проверенный список значений (все поля, кроме №, обязательны)."""
    if not isinstance(d, dict):
        raise ValueError('ожидался объект JSON')
    z = [privesti(p, d.get(p)) for p in POLYA]
    pustye = [n for n, v in zip(ZAG[1:], z[1:]) if v is None]
    if pustye:
        raise ValueError('Не заполнено: ' + ', '.join(pustye))
    if z[4] == 0:
        raise ValueError('Срок сохранения формы должен быть > 0')
    return z


def data(tekst, nazv):
    try:
        return datetime.strptime(tekst.strip(), FD).date()
    except ValueError:
        raise ValueError(nazv + ': нужна дата ДД.ММ.ГГГГ') from None


class Baza:
    def __init__(self, put):
        self.con = sqlite3.connect(put)
        self.con.create_function('low', 1, lambda s: s and s.lower(), deterministic=True)  # LIKE для кириллицы
        self.sql('CREATE TABLE IF NOT EXISTS lyzhniki (id INTEGER PRIMARY KEY, fio TEXT NOT NULL, '
                 'razryad TEXT, do_formy INTEGER, v_forme INTEGER, pobedy INTEGER)')

    def sql(self, q, par=(), mnogo=False):
        with self.con:  # одна транзакция: commit при успехе, rollback при ошибке
            return (self.con.executemany if mnogo else self.con.execute)(q, par)

    def vse(self, gde='', par=()):
        return self.sql(f'SELECT * FROM lyzhniki {gde} ORDER BY id', par).fetchall()

    def dobavit(self, z):
        return self.sql('INSERT INTO lyzhniki VALUES (?,?,?,?,?,?)', z).lastrowid

    def izmenit(self, z):
        return self.sql('UPDATE lyzhniki SET fio=?, razryad=?, do_formy=?, v_forme=?, pobedy=? WHERE id=?',
                        z[1:] + z[:1]).rowcount

    def udalit(self, n):
        return self.sql('DELETE FROM lyzhniki WHERE id=?', (n,)).rowcount

    def ochistit(self):
        self.sql('DELETE FROM lyzhniki')

    def poisk(self, filtr):
        """Живой поиск: каждое заполненное поле ищется как подстрока, без учёта регистра."""
        usl, par = [], []
        for p, v in filtr.items():
            v = v.strip().lower()
            if v:
                usl.append(f'low(CAST({p} AS TEXT)) LIKE ?')
                par.append(f'%{v}%')
        return self.vse('WHERE ' + ' AND '.join(usl) if usl else '', par)

    def poisk_odno(self, v, pole=None):
        """Адаптивный поиск: подстрока в выбранном поле или в любом, без учёта регистра."""
        v = v.strip().lower()
        if not v:
            return self.vse()
        polya = [pole] if pole else POLYA
        usl = ' OR '.join(f'low(CAST({p} AS TEXT)) LIKE ?' for p in polya)
        return self.vse('WHERE ' + usl, [f'%{v}%'] * len(polya))

    def import_json(self, put):
        """Файл: список лыжников или {"sorevnovanie": {...}, "lyzhniki": [...]}."""
        with open(put, encoding='utf-8') as f:
            d = json.load(f)
        d = {'lyzhniki': d} if isinstance(d, list) else d
        if not isinstance(d, dict) or not isinstance(d.get('lyzhniki'), list):
            raise ValueError("В файле нет списка 'lyzhniki'")
        zapisi = []
        for i, z in enumerate(d['lyzhniki'], 1):
            try:
                zapisi.append(zapis(z))
            except ValueError as e:
                raise ValueError(f'Запись {i}: {e}') from None
        self.sql('INSERT OR REPLACE INTO lyzhniki VALUES (?,?,?,?,?,?)', zapisi, mnogo=True)
        s = d.get('sorevnovanie')
        return len(zapisi), s if isinstance(s, dict) else {}

    def export_json(self, put, sorev, rez=None):
        d = {'sorevnovanie': sorev, 'lyzhniki': [dict(zip(POLYA, z)) for z in self.vse()]}
        if rez:
            fio = lambda ls: [x['fio'] for x in ls]
            d['rezultat'] = {
                'osnovnoy_sostav': fio(rez['reiting'][:OSNOVA]),
                'rezerv': fio(rez['reiting'][OSNOVA:OSNOVA + REZERV]),
                'raspredelenie': {g: fio(ls) for g, ls in rez['gruppy'].items()},
                'po_nedelyam': [{'s': a.strftime(FD), 'po': b.strftime(FD), 'lyzhniki': f} for a, b, f in rez['nedeli']]}
        with open(put, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        return len(d['lyzhniki'])


def analiz(zapisi, podg, nach, kon):
    """Пик формы каждого лыжника, его пересечение с соревнованием, группы, недели, команда."""
    if kon < nach or nach < podg:
        raise ValueError('Нужно: начало подготовки <= начало соревнования <= конец')
    dney, ls = (kon - nach).days + 1, []
    for z in zapisi:
        x = dict(zip(POLYA, z))
        s = x['pik_s'] = podg + timedelta(weeks=x['do_formy'])
        po = x['pik_po'] = s + timedelta(weeks=x['v_forme'], days=-1)
        d = x['dney'] = max(0, (min(po, kon) - max(s, nach)).days + 1)  # дней в форме на соревновании
        x['status'] = GRUPPY[0 if d == dney else 1 if d else 2 if po < nach else 3]
        ls.append(x)
    # рейтинг: дни в форме -> разряд -> победы; первые 5 - основа, следующие 2 - резерв
    ls.sort(key=lambda x: (-x['dney'], RAZRYADY.index(x['razryad']), -x['pobedy'], x['fio']))
    for m, x in enumerate(ls, 1):
        x['mesto'], x['sostav'] = m, 'основной' if m <= OSNOVA else 'резерв' if m <= OSNOVA + REZERV else ''
    nedeli = [(a, min(a + timedelta(6), kon)) for a in (nach + timedelta(weeks=i) for i in range((dney + 6) // 7))]
    return {'dney': dney, 'reiting': ls, 'daty': (podg, nach, kon),
            'gruppy': {g: [x for x in ls if x['status'] == g] for g in GRUPPY},
            'nedeli': [(a, b, [x['fio'] for x in ls if x['pik_s'] <= b and x['pik_po'] >= a]) for a, b in nedeli]}



def ust(e, v):
    e.delete(0, tk.END)
    e.insert(0, v)


def bezopasno(metod):
    """Ошибки ввода/файлов/БД в любом обработчике кнопки -> messagebox."""
    def obertka(self, *a):
        try:
            return metod(self, *a)
        except (ValueError, OSError, sqlite3.Error) as e:
            mb.showerror('Ошибка', str(e))
    return obertka


class Prilozhenie(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Лаб.14 - JSON, список команды лыжников (ИСТбд-22, вариант 9)')
        self.geometry('1100x740')
        self.bd, self.rez = Baza(BD), None
        p = ttk.Frame(self)
        p.pack(fill=tk.X, padx=8, pady=4)
        knopki = (('Импорт JSON в БД', self.importirovat), ('Сохранить в JSON', self.sohranit),
                  ('Просмотр БД', self.pokazat), ('Вычислить значения', self.vychislit),
                  ('Очистить БД', self.ochistit), ('Ввести запись', self.vvesti), ('Перейти к записи', self.pereiti),
                  ('Редактировать запись', self.redaktirovat), ('Удалить запись', self.udalit),
                  ('Поиск по полям', self.iskat))
        for i, (t, c) in enumerate(knopki):
            ttk.Button(p, text=t, command=c, width=22).grid(row=i // 5, column=i % 5, padx=2, pady=2)
        self.status = ttk.Label(p)
        self.status.grid(row=0, column=5, rowspan=2, padx=10)
        self.daty = self.ramka('Соревнование (ДД.ММ.ГГГГ)', DATY.values(), 3)
        for e, v in zip(self.daty, ('02.11.2026', '04.01.2027', '24.01.2027')):
            ust(e, v)
        self.polya = self.ramka('Поля поиска и редактирования', ZAG, 3, side=tk.BOTTOM)
        self.knopka_ochistki = ttk.Button(self.polya[0].master, text='Очистить поля', command=self.ochistit_polya)
        self.knopka_ochistki.grid(row=0, column=6, rowspan=2, padx=10)
        f = ttk.LabelFrame(self, text='Адаптивный поиск')
        f.pack(fill=tk.X, padx=8, pady=4)
        self.gde = ttk.Combobox(f, values=('Любое поле',) + ZAG, state='readonly', width=24)
        self.gde.current(0)
        self.gde.pack(side=tk.LEFT, padx=3, pady=3)
        self.stroka = ttk.Entry(f, width=50)
        self.stroka.pack(side=tk.LEFT, padx=3, pady=3)
        self.stroka.bind('<KeyRelease>', self.zhivoy_poisk)
        self.gde.bind('<<ComboboxSelected>>', self.zhivoy_poisk)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.tab = self.vkladka('БД', ttk.Treeview, columns=POLYA, show='headings')
        for p, z in zip(POLYA, ZAG):
            self.tab.heading(p, text=z)
            self.tab.column(p, width={'id': 50, 'fio': 260}.get(p, 140))
        self.tab.bind('<<TreeviewSelect>>', self.v_formu)
        self.tekst = self.vkladka('Вычисленные характеристики', tk.Text, wrap=tk.NONE, font=('Consolas', 10))
        self.holst = self.vkladka('Диаграмма формы', tk.Canvas, bg='white')
        self.holst.bind('<Configure>', lambda _: self.risovat())
        self.izmenilos()

    # --- построение окна ---
    def ramka(self, nazv, metki, kolonok, side=tk.TOP):
        f = ttk.LabelFrame(self, text=nazv)
        f.pack(side=side, fill=tk.X, padx=8, pady=4)
        polya = []
        for i, m in enumerate(metki):
            r, c = divmod(i, kolonok)
            ttk.Label(f, text=m).grid(row=r, column=2 * c, sticky=tk.E, padx=3, pady=2)
            e = (ttk.Combobox(f, values=('',) + RAZRYADY, width=10) if m == 'Разряд'
                 else ttk.Entry(f, width=34 if m.startswith('ФИО') else 12))
            e.grid(row=r, column=2 * c + 1, sticky=tk.W, padx=3, pady=2)
            polya.append(e)
        return polya

    def vkladka(self, nazv, klass, **kw):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text=nazv)
        w = klass(f, **kw)
        sb = ttk.Scrollbar(f, command=w.yview)
        w.configure(yscrollcommand=sb.set)
        w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        return w

    # --- вспомогательные ---
    def pokazat(self, zapisi=None, nadpis='Записей в БД'):
        if zapisi is None:  # показываем всю БД - строка поиска больше не действует
            zapisi = self.bd.vse()
            ust(self.stroka, '')
        self.nb.select(0)
        self.tab.delete(*self.tab.get_children())
        for z in zapisi:
            self.tab.insert('', tk.END, iid=str(z[0]), values=z)
        self.status['text'] = f'{nadpis}: {len(zapisi)}'

    def izmenilos(self):
        """Данные изменились - старый расчёт неактуален."""
        self.rez = None
        self.vyvod('Нажмите «Вычислить значения».')
        self.risovat()
        self.pokazat()

    def vyvod(self, tekst):
        self.tekst.configure(state=tk.NORMAL)
        self.tekst.delete('1.0', tk.END)
        self.tekst.insert(tk.END, tekst)
        self.tekst.configure(state=tk.DISABLED)

    def v_formu(self, _=None):
        for s in self.tab.selection()[:1]:
            for e, v in zip(self.polya, self.tab.item(s, 'values')):
                ust(e, v)

    def forma(self):
        return {p: e.get() for p, e in zip(POLYA, self.polya)}

    def nomer(self):
        n = privesti('id', self.polya[0].get())
        if n is None:
            raise ValueError('Введите номер записи (№)')
        return n

    def vydelit(self, n):
        self.nb.select(0)
        self.tab.selection_set(str(n))
        self.tab.see(str(n))

    # --- кнопки ---
    @bezopasno
    def importirovat(self):
        put = filedialog.askopenfilename(title='JSON файл', filetypes=TIPY, initialdir=PAPKA)
        if put:
            n, sorev = self.bd.import_json(put)
            for e, k in zip(self.daty, DATY):
                if sorev.get(k):
                    ust(e, sorev[k])
            self.izmenilos()
            mb.showinfo('Импорт', f'Импортировано записей: {n}')

    @bezopasno
    def sohranit(self):
        put = filedialog.asksaveasfilename(defaultextension='.json', filetypes=TIPY,
                                           initialdir=PAPKA, initialfile='komanda.json')
        if put:
            sorev = {k: e.get().strip() for k, e in zip(DATY, self.daty)}
            n = self.bd.export_json(put, sorev, self.rez)
            mb.showinfo('Сохранение', f'Сохранено записей: {n}' + (' + результат расчёта' if self.rez else ''))

    @bezopasno
    def vychislit(self):
        zapisi = self.bd.vse()
        if not zapisi:
            raise ValueError('БД пуста - импортируйте JSON или введите записи')
        r = self.rez = analiz(zapisi, *(data(e.get(), n) for e, n in zip(self.daty, DATY.values())))
        f = lambda d: d.strftime(FD)
        podg, nach, kon = r['daty']
        s = [f'Подготовка с {f(podg)}; соревнование {f(nach)} - {f(kon)} ({r["dney"]} дн.); лыжников: {len(zapisi)}',
             '', '1. РАСПРЕДЕЛЕНИЕ ПО МАКСИМАЛЬНОЙ СПОРТИВНОЙ ФОРМЕ',
             f'{"Место":<6}{"ФИО":<28}{"Разряд":<8}{"Пик формы":<25}{"Дней в форме":<14}{"Статус":<18}Побед', '-' * 92]
        s += [f'{x["mesto"]:<6}{x["fio"][:27]:<28}{x["razryad"]:<8}{f(x["pik_s"]) + " - " + f(x["pik_po"]):<25}'
              f'{x["dney"]:<14}{x["status"]:<18}{x["pobedy"]}' for x in r['reiting']]
        s += ['', 'По группам:'] + [f'  {g:<18}{len(ls):>2} чел. ' + ', '.join(x['fio'] for x in ls)
                                    for g, ls in r['gruppy'].items()]
        s += ['', 'По неделям соревнования (в пике формы хотя бы 1 день):']
        s += [f'  {i}) {f(a)} - {f(b)}: {len(fio)} чел.' for i, (a, b, fio) in enumerate(r['nedeli'], 1)]
        s += ['', f'2. КОМАНДА ({OSNOVA} основной состав + {REZERV} резерв), отбор: дни в форме -> разряд -> победы']
        for nazv, k in (('Основной состав', 'основной'), ('Резерв', 'резерв')):
            s += [nazv + ':'] + [f'  {x["mesto"]}. {x["fio"]} ({x["razryad"]}, побед {x["pobedy"]}, '
                                 f'в форме {x["dney"]} дн.)' for x in r['reiting'] if x['sostav'] == k]
        if len(zapisi) < OSNOVA + REZERV:
            s.append(f'! Лыжников меньше {OSNOVA + REZERV} - команда неполная')
        vne = [x['fio'] for x in r['reiting'] if x['sostav'] and not x['dney']]
        if vne:
            s.append('! В команде лыжники вне пика формы: ' + ', '.join(vne))
        self.vyvod('\n'.join(s))
        self.risovat()
        self.nb.select(1)

    def risovat(self):
        """Диаграмма: полоса пика формы каждого лыжника на фоне периода соревнования."""
        c, r = self.holst, self.rez
        c.delete('all')
        if not r:
            return c.create_text(20, 20, anchor=tk.NW, text='Нажмите «Вычислить значения».')
        (podg, nach, kon), ls = r['daty'], r['reiting']
        w, lev, verh, h = max(c.winfo_width(), 600), 210, 50, 24
        dn = (max([kon] + [x['pik_po'] for x in ls]) - podg).days + 8
        X = lambda d, plus=0: lev + ((d - podg).days + plus) / dn * (w - lev - 20)
        niz = verh + h * len(ls)
        c.create_rectangle(X(nach), verh - 8, X(kon, 1), niz, fill='#dce6ff', outline='#5577cc')
        for n in range(0, dn // 7 + 1, 2):
            xx = X(podg, 7 * n)
            c.create_line(xx, verh - 8, xx, niz, fill='#ddd')
            c.create_text(xx, niz + 4, anchor=tk.N, text=n, font=('Arial', 8))
        c.create_text(lev, niz + 18, anchor=tk.NW, text='недели от начала подготовки', font=('Arial', 8))
        for i, x in enumerate(ls):
            y = verh + i * h
            c.create_text(lev - 6, y + h / 2, anchor=tk.E, text=f'{x["mesto"]}. {x["fio"][:24]}')
            c.create_rectangle(X(x['pik_s']), y + 5, X(x['pik_po'], 1), y + h - 5, fill=CVET[x['sostav']], outline='')
        for j, (_, cv, t) in enumerate(LEGENDA):
            c.create_rectangle(lev + j * 150, 12, lev + j * 150 + 14, 26, fill=cv, outline='')
            c.create_text(lev + j * 150 + 20, 19, anchor=tk.W, text=t)
        c.configure(scrollregion=(0, 0, w, niz + 40))

    @bezopasno
    def vvesti(self):
        n = self.bd.dobavit(zapis(self.forma()))
        ust(self.polya[0], n)
        self.izmenilos()
        self.vydelit(n)

    @bezopasno
    def pereiti(self):
        """По № или, если он пуст, к первой записи, подходящей по заполненным полям."""
        nashli = None
        if self.polya[0].get().strip():
            n = self.nomer()
        else:
            f = self.forma()
            if not any(v.strip() for v in f.values()):
                raise ValueError('Заполните № или любое другое поле')
            nashli = self.bd.poisk(f)
            if not nashli:
                raise ValueError('По заполненным полям записей не найдено')
            n = nashli[0][0]
        if not self.tab.exists(str(n)):
            self.pokazat()
        if not self.tab.exists(str(n)):
            raise ValueError(f'Запись {n} не найдена')
        self.vydelit(n)
        self.status['text'] = f'Переход к записи № {n}' + (f' (подходит записей: {len(nashli)})' if nashli else '')

    @bezopasno
    def redaktirovat(self):
        z = zapis(self.forma())
        if z[0] is None:
            raise ValueError('Номер записи (№) обязателен')
        if not self.bd.izmenit(z):
            raise ValueError(f'Запись {z[0]} не найдена')
        self.izmenilos()
        self.vydelit(z[0])

    @bezopasno
    def udalit(self):
        n = self.nomer()
        if mb.askyesno('Удаление', f'Удалить запись {n}?'):
            if not self.bd.udalit(n):
                raise ValueError(f'Запись {n} не найдена')
            self.izmenilos()

    @bezopasno
    def iskat(self):
        self.pokazat(self.bd.poisk(self.forma()), 'Найдено записей')

    def zhivoy_poisk(self, _=None):
        i = self.gde.current()
        self.pokazat(self.bd.poisk_odno(self.stroka.get(), POLYA[i - 1] if i else None), 'Найдено записей')

    def ochistit_polya(self):
        for e in self.polya:
            ust(e, '')
        self.tab.selection_remove(*self.tab.selection())  # чтобы клик по той же строке снова заполнил поля

    def ochistit(self):
        if mb.askyesno('Очистка БД', 'Удалить все записи из БД?'):
            self.bd.ochistit()
            self.izmenilos()


if __name__ == '__main__':
    Prilozhenie().mainloop()
