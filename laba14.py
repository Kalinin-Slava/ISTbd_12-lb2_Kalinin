# Лаба 14 - обработка JSON файлов, без pandas
# группа ИСТбд-22, вариант 9 "Список команды"
# лыжник: ФИО, разряд, срок достижения макс. спортивной формы (нед.),
# срок сохранения макс. формы (нед.), победы.
# Ввод: начало и конец соревнования (+ дата начала подготовки, от неё считаются недели).
# Обработка: распределение лыжников по макс. спортивной форме в течение соревнований,
# формирование команды (5 - основной состав, 2 - резерв).

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import json
import os
from datetime import datetime, timedelta

PAPKA = os.path.dirname(os.path.abspath(__file__))
PUT_BD = os.path.join(PAPKA, 'komanda.db')
PUT_JSON = os.path.join(PAPKA, 'komanda.json')
FORMAT_DATY = '%d.%m.%Y'
OSNOVA = 5
REZERV = 2

POLYA = ['id', 'fio', 'razryad', 'do_formy', 'v_forme', 'pobedy']
ZAGOLOVKI = {'id': '№', 'fio': 'ФИО лыжника', 'razryad': 'Разряд',
             'do_formy': 'До пика формы, нед.', 'v_forme': 'Сохранение формы, нед.', 'pobedy': 'Победы'}
CELYE = {'id', 'do_formy', 'v_forme', 'pobedy'}
# от сильного разряда к слабому - индекс используется при сортировке
RAZRYADY = ['МСМК', 'МС', 'КМС', 'I', 'II', 'III', 'б/р']
SINONIMY = {'1': 'I', '2': 'II', '3': 'III'}

DATY = ['podgotovka', 'nachalo', 'konec']
ZAGOLOVKI_DAT = {'podgotovka': 'Начало подготовки', 'nachalo': 'Начало соревнования',
                 'konec': 'Конец соревнования'}

VSTAVKA = "INSERT INTO lyzhniki VALUES (" + ",".join("?" * len(POLYA)) + ")"


# ---------------- backend ----------------

def podklyuchit():
    return sqlite3.connect(PUT_BD)


def sozdat_tablitsu(con):
    con.execute("""CREATE TABLE IF NOT EXISTS lyzhniki (
        id       INTEGER PRIMARY KEY,
        fio      TEXT NOT NULL,
        razryad  TEXT,
        do_formy INTEGER,
        v_forme  INTEGER,
        pobedy   INTEGER)""")
    con.commit()


def privesti(pole, znach):
    # пустая строка -> None, целые поля -> int, разряд -> из списка RAZRYADY
    if znach is None:
        return None
    znach = str(znach).strip()
    if znach == '':
        return None
    if pole in CELYE:
        chislo = int(znach)
        if chislo < 0:
            raise ValueError(ZAGOLOVKI[pole] + ": значение не может быть отрицательным")
        return chislo
    if pole == 'razryad':
        znach = SINONIMY.get(znach, znach)
        if znach not in RAZRYADY:
            raise ValueError("Разряд должен быть одним из: " + ", ".join(RAZRYADY))
    return znach


def proverit_zapis(znach):
    # для ввода/редактирования все поля, кроме id, обязательны
    for p, v in zip(POLYA[1:], znach[1:]):
        if v is None:
            raise ValueError("Не заполнено поле: " + ZAGOLOVKI[p])
    if znach[POLYA.index('v_forme')] == 0:
        raise ValueError("Срок сохранения формы должен быть больше 0")
    return znach


def razobrat_datu(tekst, nazv):
    try:
        return datetime.strptime(tekst.strip(), FORMAT_DATY).date()
    except ValueError:
        raise ValueError(nazv + ": нужна дата в формате ДД.ММ.ГГГГ")


class Lyzhnik:
    def __init__(self, slovar):
        # один объект JSON -> один лыжник, значения сразу приводятся к типам БД
        self.znach = proverit_zapis([privesti(p, slovar.get(p)) for p in POLYA])


def zagruzit_json(put):
    # файл - либо список лыжников, либо {"sorevnovanie": {...}, "lyzhniki": [...]}
    with open(put, 'r', encoding='utf-8') as f:
        dannye = json.load(f)
    if isinstance(dannye, list):
        dannye = {'lyzhniki': dannye}
    if not isinstance(dannye, dict) or not isinstance(dannye.get('lyzhniki'), list):
        raise ValueError("В файле нет списка 'lyzhniki'")
    spisok = []
    for nomer, z in enumerate(dannye['lyzhniki'], 1):
        if not isinstance(z, dict):
            raise ValueError(f"Запись {nomer}: ожидался объект JSON")
        try:
            spisok.append(Lyzhnik(z))
        except ValueError as oshibka:
            raise ValueError(f"Запись {nomer}: {oshibka}")
    sorev = dannye.get('sorevnovanie') if isinstance(dannye.get('sorevnovanie'), dict) else {}
    return spisok, sorev


def import_json(con, put):
    sozdat_tablitsu(con)
    spisok, sorev = zagruzit_json(put)
    # записи без id получают новый номер, с id - заменяют существующие
    con.executemany(VSTAVKA.replace("INSERT", "INSERT OR REPLACE", 1), [l.znach for l in spisok])
    con.commit()
    return len(spisok), sorev


def sohranit_json(con, put, sorev, rez=None):
    dannye = {'sorevnovanie': sorev,
              'lyzhniki': [dict(zip(POLYA, z)) for z in vse_zapisi(con)]}
    if rez is not None:
        dannye['rezultat'] = {
            'osnovnoy_sostav': [l['fio'] for l in rez['osnova']],
            'rezerv': [l['fio'] for l in rez['rezerv']],
            'raspredelenie': {k: [l['fio'] for l in v] for k, v in rez['gruppy'].items()},
            'v_forme_po_nedelyam': [{'nedelya': n['nomer'], 's': n['s'].strftime(FORMAT_DATY),
                                     'po': n['po'].strftime(FORMAT_DATY), 'lyzhniki': n['fio']}
                                    for n in rez['nedeli']]}
    with open(put, 'w', encoding='utf-8') as f:
        json.dump(dannye, f, ensure_ascii=False, indent=2)
    return len(dannye['lyzhniki'])


def vse_zapisi(con):
    return con.execute("SELECT * FROM lyzhniki ORDER BY id").fetchall()


def odna_zapis(con, id_l):
    return con.execute("SELECT * FROM lyzhniki WHERE id = ?", (id_l,)).fetchone()


def dobavit_zapis(con, znach):
    cur = con.execute(VSTAVKA, znach)
    con.commit()
    return cur.lastrowid


def izmenit_zapis(con, znach):
    sets = ", ".join(p + " = ?" for p in POLYA[1:])
    cur = con.execute("UPDATE lyzhniki SET " + sets + " WHERE id = ?", znach[1:] + [znach[0]])
    con.commit()
    return cur.rowcount


def udalit_zapis(con, id_l):
    cur = con.execute("DELETE FROM lyzhniki WHERE id = ?", (id_l,))
    con.commit()
    return cur.rowcount


def poisk(con, filtry):
    # filtry - словарь поле -> строка; ФИО ищем по подстроке, остальное - точно
    usl, par = [], []
    for pole, znach in filtry.items():
        if znach.strip() == '':
            continue
        if pole == 'fio':
            usl.append("fio LIKE ?")
            par.append("%" + znach.strip() + "%")
        else:
            usl.append(pole + " = ?")
            par.append(privesti(pole, znach))
    sql = "SELECT * FROM lyzhniki"
    if usl:
        sql += " WHERE " + " AND ".join(usl)
    return con.execute(sql + " ORDER BY id", par).fetchall()


def ochistit_bd(con):
    con.execute("DELETE FROM lyzhniki")
    con.commit()


def analiz_variant_9(zapisi, podgotovka, nachalo, konec):
    if konec < nachalo:
        raise ValueError("Конец соревнования раньше начала")
    if nachalo < podgotovka:
        raise ValueError("Соревнование начинается раньше начала подготовки")
    dney = (konec - nachalo).days + 1

    # 1. пик формы каждого лыжника и его пересечение с соревнованием (в днях, включительно)
    lyzhniki = []
    for z in zapisi:
        l = dict(zip(POLYA, z))
        l['pik_s'] = podgotovka + timedelta(weeks=l['do_formy'])
        l['pik_po'] = l['pik_s'] + timedelta(weeks=l['v_forme'], days=-1)
        s, po = max(l['pik_s'], nachalo), min(l['pik_po'], konec)
        l['dney_v_forme'] = max(0, (po - s).days + 1)
        if l['dney_v_forme'] == dney:
            l['status'] = 'весь период'
        elif l['dney_v_forme'] > 0:
            l['status'] = 'частично'
        elif l['pik_po'] < nachalo:
            l['status'] = 'пик до старта'
        else:
            l['status'] = 'пик после финиша'
        lyzhniki.append(l)

    # 2. распределение по группам
    gruppy = {k: [] for k in ('весь период', 'частично', 'пик до старта', 'пик после финиша')}
    for l in lyzhniki:
        gruppy[l['status']].append(l)

    # 3. распределение по неделям соревнования: кто в пике формы хотя бы день недели
    nedeli = []
    s = nachalo
    while s <= konec:
        po = min(s + timedelta(days=6), konec)
        nedeli.append({'nomer': len(nedeli) + 1, 's': s, 'po': po,
                       'fio': [l['fio'] for l in lyzhniki if l['pik_s'] <= po and l['pik_po'] >= s]})
        s = po + timedelta(days=1)

    # 4. рейтинг: дни в форме, затем разряд, затем победы
    reiting = sorted(lyzhniki, key=lambda l: (-l['dney_v_forme'], RAZRYADY.index(l['razryad']),
                                               -l['pobedy'], l['fio']))
    for mesto, l in enumerate(reiting, 1):
        l['mesto'] = mesto
        l['sostav'] = 'основной' if mesto <= OSNOVA else 'резерв' if mesto <= OSNOVA + REZERV else ''
    return {'dney': dney, 'lyzhniki': lyzhniki, 'gruppy': gruppy, 'nedeli': nedeli,
            'reiting': reiting, 'osnova': reiting[:OSNOVA],
            'rezerv': reiting[OSNOVA:OSNOVA + REZERV],
            'podgotovka': podgotovka, 'nachalo': nachalo, 'konec': konec}


# ---------------- frontend ----------------

class Prilozhenie(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Лаб.14 - JSON, список команды лыжников, ИСТбд-22 вариант 9")
        self.geometry("1100x760")
        self.con = podklyuchit()
        sozdat_tablitsu(self.con)
        self.rez = None

        # панель кнопок (два ряда)
        panel = tk.Frame(self)
        panel.pack(fill=tk.X, padx=10, pady=5)
        knopki = [("Импорт JSON в БД", self.importirovat),
                  ("Сохранить в JSON", self.sohranit),
                  ("Просмотр БД", self.obnovit_tablitsu),
                  ("Вычислить значения", self.vychislit),
                  ("Очистить БД", self.ochistit),
                  ("Ввести запись", self.vvesti),
                  ("Перейти к записи", self.pereiti),
                  ("Редактировать запись", self.redaktirovat),
                  ("Удалить запись", self.udalit),
                  ("Поиск по полям", self.iskat)]
        for i, (tekst, cmd) in enumerate(knopki):
            tk.Button(panel, text=tekst, command=cmd, width=20).grid(row=i // 5, column=i % 5, padx=4, pady=2)

        self.status = tk.Label(panel, text="БД пуста")
        self.status.grid(row=0, column=5, rowspan=2, padx=10)

        # ввод параметров соревнования
        ramka_daty = tk.LabelFrame(self, text="Соревнование (ДД.ММ.ГГГГ)")
        ramka_daty.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.daty = {}
        po_umolch = {'podgotovka': '02.11.2026', 'nachalo': '04.01.2027', 'konec': '24.01.2027'}
        for i, d in enumerate(DATY):
            tk.Label(ramka_daty, text=ZAGOLOVKI_DAT[d]).grid(row=0, column=i * 2, sticky=tk.E, padx=3, pady=3)
            e = tk.Entry(ramka_daty, width=12)
            e.insert(0, po_umolch[d])
            e.grid(row=0, column=i * 2 + 1, padx=(3, 15), pady=3)
            self.daty[d] = e

        # вкладки
        vkladki = ttk.Notebook(self)
        vkladki.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        vkl_dannye = tk.Frame(vkladki)
        vkladki.add(vkl_dannye, text="БД")
        self.tablitsa = ttk.Treeview(vkl_dannye, columns=POLYA, show='headings', height=15)
        for p in POLYA:
            self.tablitsa.heading(p, text=ZAGOLOVKI[p])
            shir = {'id': 50, 'fio': 280, 'razryad': 80}.get(p, 150)
            self.tablitsa.column(p, width=shir, anchor=tk.W)
        skrol = ttk.Scrollbar(vkl_dannye, orient=tk.VERTICAL, command=self.tablitsa.yview)
        self.tablitsa.configure(yscroll=skrol.set)
        self.tablitsa.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        skrol.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.tablitsa.bind('<<TreeviewSelect>>', self.vybor_stroki)

        vkl_rezult = tk.Frame(vkladki)
        vkladki.add(vkl_rezult, text="Вычисленные характеристики")
        self.tekst_rezult = tk.Text(vkl_rezult, wrap=tk.NONE, state=tk.DISABLED, font=("Consolas", 10))
        skrol_r = ttk.Scrollbar(vkl_rezult, orient=tk.VERTICAL, command=self.tekst_rezult.yview)
        self.tekst_rezult.configure(yscroll=skrol_r.set)
        self.tekst_rezult.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        skrol_r.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        vkl_diagr = tk.Frame(vkladki)
        vkladki.add(vkl_diagr, text="Диаграмма формы")
        self.holst = tk.Canvas(vkl_diagr, bg='white')
        skrol_d = ttk.Scrollbar(vkl_diagr, orient=tk.VERTICAL, command=self.holst.yview)
        self.holst.configure(yscrollcommand=skrol_d.set)
        self.holst.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        skrol_d.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.holst.bind('<Configure>', lambda _: self.narisovat())
        self.vkladki = vkladki

        # поля поиска и редактирования
        ramka_pola = tk.LabelFrame(self, text="Поля поиска и редактирования")
        ramka_pola.pack(fill=tk.X, padx=10, pady=(0, 8))
        self.polya = {}
        for i, p in enumerate(POLYA):
            tk.Label(ramka_pola, text=ZAGOLOVKI[p]).grid(row=i % 2, column=(i // 2) * 2, sticky=tk.E, padx=3, pady=2)
            if p == 'razryad':
                e = ttk.Combobox(ramka_pola, values=[''] + RAZRYADY, width=10)
            else:
                e = tk.Entry(ramka_pola, width=34 if p == 'fio' else 12)
            e.grid(row=i % 2, column=(i // 2) * 2 + 1, padx=3, pady=2, sticky=tk.W)
            self.polya[p] = e

        self.obnovit_tablitsu()

    # --- вспомогательные ---
    def pokazat(self, zapisi, tekst=None):
        self.vkladki.select(0)
        self.tablitsa.delete(*self.tablitsa.get_children())
        for z in zapisi:
            self.tablitsa.insert('', tk.END, iid=str(z[0]), values=['' if v is None else v for v in z])
        self.status.config(text=tekst or ("Записей в БД: " + str(len(zapisi))))

    def sobrat_polya(self):
        return [privesti(p, self.polya[p].get()) for p in POLYA]

    def vybor_stroki(self, _=None):
        vyb = self.tablitsa.selection()
        if not vyb:
            return
        znach = self.tablitsa.item(vyb[0], 'values')
        for p, v in zip(POLYA, znach):
            self.polya[p].delete(0, tk.END)
            self.polya[p].insert(0, v)

    def id_iz_polya(self):
        try:
            return int(self.polya['id'].get())
        except ValueError:
            messagebox.showwarning("Ошибка", "Введите числовой номер записи (№).")
            return None

    def sobrat_daty(self):
        return {d: razobrat_datu(self.daty[d].get(), ZAGOLOVKI_DAT[d]) for d in DATY}

    def vyvesti_tekst(self, stroki):
        self.tekst_rezult.configure(state=tk.NORMAL)
        self.tekst_rezult.delete('1.0', tk.END)
        self.tekst_rezult.insert(tk.END, "\n".join(stroki))
        self.tekst_rezult.configure(state=tk.DISABLED)

    def sbrosit_rezultat(self):
        # данные изменились - старый расчёт больше не актуален
        self.rez = None
        self.narisovat()

    # --- кнопки ---
    def importirovat(self):
        put = filedialog.askopenfilename(
            title="Выберите JSON файл",
            filetypes=(("JSON файлы", "*.json"), ("Все файлы", "*.*")),
            initialdir=PAPKA)
        if not put:
            return
        try:
            kol, sorev = import_json(self.con, put)
        except (OSError, ValueError, sqlite3.Error) as oshibka:
            messagebox.showerror("Ошибка импорта", str(oshibka))
            return
        for d in DATY:
            if sorev.get(d):
                self.daty[d].delete(0, tk.END)
                self.daty[d].insert(0, str(sorev[d]))
        self.sbrosit_rezultat()
        self.obnovit_tablitsu()
        messagebox.showinfo("Импорт", "Импортировано записей: " + str(kol))

    def sohranit(self):
        put = filedialog.asksaveasfilename(
            title="Сохранить набор данных в JSON", defaultextension=".json",
            filetypes=(("JSON файлы", "*.json"), ("Все файлы", "*.*")),
            initialdir=PAPKA, initialfile=os.path.basename(PUT_JSON))
        if not put:
            return
        sorev = {d: self.daty[d].get().strip() for d in DATY}
        try:
            kol = sohranit_json(self.con, put, sorev, self.rez)
        except OSError as oshibka:
            messagebox.showerror("Ошибка сохранения", str(oshibka))
            return
        dop = " (с результатами расчёта)" if self.rez else ""
        messagebox.showinfo("Сохранение", f"Сохранено записей: {kol}{dop}\n{put}")

    def obnovit_tablitsu(self):
        self.pokazat(vse_zapisi(self.con))

    def vychislit(self):
        zapisi = vse_zapisi(self.con)
        if not zapisi:
            self.sbrosit_rezultat()
            self.vyvesti_tekst(["ВАРИАНТ 9 (ИСТбд-22)", "=" * 60, "Нет данных. Импортируйте JSON в БД."])
            self.vkladki.select(1)
            return
        try:
            d = self.sobrat_daty()
            r = analiz_variant_9(zapisi, d['podgotovka'], d['nachalo'], d['konec'])
        except ValueError as oshibka:
            messagebox.showerror("Ошибка ввода", str(oshibka))
            return
        self.rez = r
        f = lambda x: x.strftime(FORMAT_DATY)
        s = ["ВАРИАНТ 9 (ИСТбд-22) - СПИСОК КОМАНДЫ", "=" * 92,
             f"Подготовка с {f(r['podgotovka'])}; соревнование {f(r['nachalo'])} - {f(r['konec'])} "
             f"({r['dney']} дн.)", f"Лыжников в БД: {len(r['lyzhniki'])}", "",
             "1. РАСПРЕДЕЛЕНИЕ ПО МАКСИМАЛЬНОЙ СПОРТИВНОЙ ФОРМЕ",
             f"{'Место':<6}{'ФИО':<28}{'Разряд':<8}{'Пик формы':<25}{'Дней в форме':<14}{'Статус':<18}Побед",
             "-" * 92]
        for l in r['reiting']:
            s.append(f"{l['mesto']:<6}{l['fio'][:27]:<28}{l['razryad']:<8}"
                     f"{f(l['pik_s']) + ' - ' + f(l['pik_po']):<25}"
                     f"{str(l['dney_v_forme']) + ' из ' + str(r['dney']):<14}{l['status']:<18}{l['pobedy']}")
        s += ["", "Итого по группам:"]
        for nazv, gr in r['gruppy'].items():
            s.append(f"  {nazv:<18} {len(gr):>2} чел." + (": " + ", ".join(l['fio'] for l in gr) if gr else ""))
        s += ["", "По неделям соревнования (в пике формы хотя бы один день):"]
        for n in r['nedeli']:
            s.append(f"  неделя {n['nomer']} ({f(n['s'])} - {f(n['po'])}): {len(n['fio'])} чел.")

        s += ["", f"2. КОМАНДА ({OSNOVA} - основной состав, {REZERV} - резерв)",
              "Отбор: больше дней в пике формы на соревновании -> выше разряд -> больше побед", ""]
        for nazv, gr in (("Основной состав", r['osnova']), ("Резерв", r['rezerv'])):
            s.append(nazv + ":")
            for l in gr:
                s.append(f"  {l['mesto']}. {l['fio']} ({l['razryad']}, побед: {l['pobedy']}, "
                         f"в форме {l['dney_v_forme']} дн.)")
        if len(r['reiting']) < OSNOVA + REZERV:
            s.append(f"! Лыжников меньше {OSNOVA + REZERV} - команда неполная.")
        vne = [l['fio'] for l in r['osnova'] + r['rezerv'] if l['dney_v_forme'] == 0]
        if vne:
            s.append("! В команду попали лыжники вне пика формы: " + ", ".join(vne))
        self.vyvesti_tekst(s)
        self.narisovat()
        self.vkladki.select(1)

    def narisovat(self):
        # диаграмма: полоса пика формы каждого лыжника на фоне периода соревнования
        c = self.holst
        c.delete('all')
        r = self.rez
        if r is None:
            c.create_text(20, 20, anchor=tk.NW, text="Нажмите «Вычислить значения».", font=("Arial", 11))
            c.configure(scrollregion=(0, 0, 0, 0))
            return
        shir = max(c.winfo_width(), 600)
        lev, verh, shag = 200, 60, 26
        t0 = r['podgotovka']
        t1 = max([r['konec']] + [l['pik_po'] for l in r['lyzhniki']]) + timedelta(days=7)
        dney = (t1 - t0).days
        x = lambda d: lev + (d - t0).days / dney * (shir - lev - 20)
        niz = verh + shag * len(r['reiting'])

        c.create_rectangle(x(r['nachalo']), verh - 10, x(r['konec'] + timedelta(days=1)), niz,
                           fill='#dce6ff', outline='#5577cc')
        c.create_text(x(r['nachalo']) + 3, verh - 12, anchor=tk.SW, text="соревнование", fill='#3355aa')
        nedelya = 0
        while t0 + timedelta(weeks=nedelya) <= t1:
            xx = x(t0 + timedelta(weeks=nedelya))
            c.create_line(xx, verh - 10, xx, niz, fill='#e0e0e0')
            if nedelya % 2 == 0:
                c.create_text(xx, niz + 4, anchor=tk.N, text=str(nedelya), font=("Arial", 8))
            nedelya += 1
        c.create_text(lev, niz + 20, anchor=tk.NW, text="недели от начала подготовки", font=("Arial", 8))

        tsvet = {'основной': '#2e9d4f', 'резерв': '#f0a020', '': '#a0a0a0'}
        for i, l in enumerate(r['reiting']):
            y = verh + i * shag
            c.create_text(lev - 8, y + shag / 2, anchor=tk.E, text=f"{l['mesto']}. {l['fio'][:24]}")
            c.create_rectangle(x(l['pik_s']), y + 5, x(l['pik_po'] + timedelta(days=1)), y + shag - 5,
                               fill=tsvet[l['sostav']], outline='')
        for j, (nazv, k) in enumerate((("основной состав", 'основной'), ("резерв", 'резерв'),
                                       ("не в команде", ''))):
            c.create_rectangle(lev + j * 150, 10, lev + j * 150 + 14, 24, fill=tsvet[k], outline='')
            c.create_text(lev + j * 150 + 20, 17, anchor=tk.W, text=nazv)
        c.configure(scrollregion=(0, 0, shir, niz + 40))

    def vvesti(self):
        try:
            znach = proverit_zapis(self.sobrat_polya())
            nov_id = dobavit_zapis(self.con, znach)
        except (ValueError, sqlite3.Error) as oshibka:
            messagebox.showerror("Ошибка добавления", str(oshibka))
            return
        self.polya['id'].delete(0, tk.END)
        self.polya['id'].insert(0, str(nov_id))
        self.sbrosit_rezultat()
        self.obnovit_tablitsu()
        self.pereiti()

    def pereiti(self):
        id_l = self.id_iz_polya()
        if id_l is None:
            return
        if odna_zapis(self.con, id_l) is None:
            messagebox.showinfo("Переход", "Запись с таким номером не найдена.")
            return
        if not self.tablitsa.exists(str(id_l)):
            self.obnovit_tablitsu()
        self.vkladki.select(0)
        self.tablitsa.selection_set(str(id_l))
        self.tablitsa.focus(str(id_l))
        self.tablitsa.see(str(id_l))

    def redaktirovat(self):
        try:
            znach = self.sobrat_polya()
            if znach[0] is None:
                raise ValueError("Номер записи (№) обязателен")
            izm = izmenit_zapis(self.con, proverit_zapis(znach))
        except (ValueError, sqlite3.Error) as oshibka:
            messagebox.showerror("Ошибка редактирования", str(oshibka))
            return
        if izm == 0:
            messagebox.showinfo("Редактирование", "Запись с таким номером не найдена.")
            return
        self.sbrosit_rezultat()
        self.obnovit_tablitsu()
        self.pereiti()

    def udalit(self):
        id_l = self.id_iz_polya()
        if id_l is None:
            return
        if not messagebox.askyesno("Удаление", f"Удалить запись {id_l}?"):
            return
        if udalit_zapis(self.con, id_l) == 0:
            messagebox.showinfo("Удаление", "Запись не найдена.")
        self.sbrosit_rezultat()
        self.obnovit_tablitsu()

    def iskat(self):
        filtry = {p: self.polya[p].get() for p in POLYA}
        try:
            nashli = poisk(self.con, filtry)
        except (ValueError, sqlite3.Error) as oshibka:
            messagebox.showerror("Ошибка поиска", str(oshibka))
            return
        self.pokazat(nashli, "Найдено записей: " + str(len(nashli)))

    def ochistit(self):
        if not messagebox.askyesno("Очистка БД", "Удалить все записи из БД?"):
            return
        ochistit_bd(self.con)
        self.obnovit_tablitsu()
        self.vychislit()


if __name__ == "__main__":
    app = Prilozhenie()
    app.mainloop()
