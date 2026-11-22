"""Native themed desktop guide; all USB/download/codec work stays off the UI thread."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
import webbrowser

from . import __version__
from .download import OFFICIAL_PAGE
from .firmware import STOCK_RESTORE_RESET,catalog
from .workflow import Workflow
from .models import model_spec


class App:
    def __init__(self,root,*,assets=None,workflow=None):
        self.root=root;self.workflow=workflow or Workflow(assets=assets)
        self.assets=assets;self.events=queue.Queue();self.busy=None
        _,self.catalog=catalog(assets)
        root.title('Lumix Firmware Updater');root.geometry('840x740');root.minsize(800,690)
        root.protocol('WM_DELETE_WINDOW',self.close)
        outer=ttk.Frame(root,padding=22);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Lumix Firmware Updater',font=('TkDefaultFont',19,'bold')).pack(anchor='w')
        ttk.Label(outer,text='Prepare an SD update, then install it using the camera.',wraplength=730).pack(anchor='w',pady=(6,18))
        self.tabs=ttk.Notebook(outer);self.tabs.pack(fill='both',expand=True)
        self.pages=[ttk.Frame(self.tabs,padding=18) for _ in range(3)]
        for page,label in zip(self.pages,('1  Camera','2  Firmware','3  Install')):self.tabs.add(page,text=label)
        self.camera_text=tk.StringVar(value='Connect an awake GM1 or GM5 in service mode, then read its firmware.')
        page=self.pages[0]
        ttk.Label(page,text='Read the connected camera',font=('TkDefaultFont',13,'bold')).pack(anchor='w')
        ttk.Label(page,textvariable=self.camera_text,wraplength=670,justify='left').pack(anchor='w',pady=(12,18))
        self.read_button=ttk.Button(page,text='Read camera',command=self.on_inspect);self.read_button.pack(anchor='w')
        ttk.Button(page,text='USB connection help',command=self.connection_help).pack(anchor='w',pady=(12,0))
        ttk.Label(page,text='Supports reviewed GM1 1.1 (0110) and GM5 1.1 (0110/0111) builds, plus compatible research patches. Other builds are checked and refused.',
            wraplength=660).pack(anchor='w',pady=(24,0))
        page=self.pages[1]
        ttk.Label(page,text='Choose the firmware',font=('TkDefaultFont',13,'bold')).pack(anchor='w')
        self.choice=tk.StringVar(value='stable')
        self.choice_buttons=[]
        self.choice_descriptions=[]
        for key in ('stable','luts','restore'):
            item=self.catalog['choices'][key]
            b=ttk.Radiobutton(page,text=item['label'],variable=self.choice,value=key);b.pack(anchor='w',pady=(13,0));self.choice_buttons.append(b)
            label=ttk.Label(page,text=item['description'],wraplength=620)
            label.pack(anchor='w',padx=23,pady=(2,0));self.choice_descriptions.append(label)
        ttk.Separator(page).pack(fill='x',pady=18)
        self.source=tk.StringVar(value='download');self.local=tk.StringVar()
        self.download_text=tk.StringVar(value='Download the official firmware for the detected camera')
        ttk.Radiobutton(page,textvariable=self.download_text,variable=self.source,value='download').pack(anchor='w')
        row=ttk.Frame(page);row.pack(fill='x',pady=(8,0))
        ttk.Radiobutton(row,text='Use an official BIN or ZIP:',variable=self.source,value='local').pack(side='left')
        ttk.Entry(row,textvariable=self.local).pack(side='left',fill='x',expand=True,padx=7)
        ttk.Button(row,text='Choose file…',command=self.choose_file).pack(side='left')
        ttk.Label(page,text='The official input and every reconstructed component are verified before saving.',wraplength=650).pack(anchor='w',pady=(12,0))
        self.build_button=ttk.Button(page,text='Prepare update and stock restore…',command=self.on_prepare,state='disabled')
        self.build_button.pack(anchor='w',pady=(18,0))
        page=self.pages[2]
        instructions=ttk.Frame(page);instructions.pack(fill='both',expand=True)
        self.steps=tk.Text(instructions,width=1,height=9,wrap='word',relief='flat',font=('TkDefaultFont',11))
        steps_scroll=ttk.Scrollbar(instructions,orient='vertical',command=self.steps.yview)
        self.steps.configure(yscrollcommand=steps_scroll.set)
        steps_scroll.pack(side='right',fill='y');self.steps.pack(side='left',fill='both',expand=True)
        self.set_steps('Prepare the firmware files first. The camera performs installation from its SD card.')
        row=ttk.Frame(page);row.pack(fill='x',pady=(12,6))
        self.open_button=ttk.Button(row,text='Open prepared folder',command=self.open_folder,state='disabled');self.open_button.pack(side='left')
        self.card=tk.BooleanVar(value=False)
        self.card_check=ttk.Checkbutton(page,text='I copied the update and inserted the card with the camera switched off.',variable=self.card)
        self.card_check.pack(anchor='w',pady=(8,4))
        self.enable_button=ttk.Button(page,text='Enable this update',command=self.on_enable,state='disabled');self.enable_button.pack(anchor='w',pady=(5,0))
        limits=ttk.Frame(page);limits.pack(fill='x',pady=(14,0))
        self.limitations=tk.Text(limits,width=1,height=4,wrap='word',relief='flat',font=('TkDefaultFont',10))
        limits_scroll=ttk.Scrollbar(limits,orient='vertical',command=self.limitations.yview)
        self.limitations.configure(yscrollcommand=limits_scroll.set)
        limits_scroll.pack(side='right',fill='y');self.limitations.pack(side='left',fill='x',expand=True)
        self.set_limitations([])
        self.status=tk.StringVar(value='Ready')
        self.bar=ttk.Progressbar(outer,mode='determinate');self.bar.pack(fill='x',pady=(15,6))
        ttk.Label(outer,textvariable=self.status,wraplength=730).pack(anchor='w')
        ttk.Label(outer,text='Version '+__version__,font=('TkDefaultFont',9)).pack(anchor='e')
        root.after(80,self.poll)

    def set_steps(self,text):
        self.steps.configure(state='normal');self.steps.delete('1.0','end');self.steps.insert('1.0',text);self.steps.configure(state='disabled')

    def set_limitations(self,items):
        self.limitations.configure(state='normal');self.limitations.delete('1.0','end')
        if items:self.limitations.insert('1.0','Patch limitations\n'+'\n'.join('• '+s for s in items))
        self.limitations.configure(state='disabled')

    def start(self,action,operation):
        if self.busy:return
        self.busy=action;self.status.set('Working…')
        for button in (self.read_button,self.build_button,self.enable_button,self.open_button):button.configure(state='disabled')
        self.card_check.configure(state='disabled')
        if action in ('inspect','prepare'):self.card.set(False)
        def progress(label,done,total):self.events.put(('progress',(label,done,total)))
        def worker():
            try:self.events.put(('done',(action,operation(progress))))
            except Exception as error:self.events.put(('error',(action,str(error))))
        threading.Thread(target=worker,name='LumixUpdater-'+action,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,payload=self.events.get_nowait()
                if kind=='progress':
                    label,done,total=payload;self.status.set(label)
                    self.bar.configure(maximum=max(1,total),value=done)
                    continue
                action,result=payload;self.busy=None;self.read_button.configure(state='normal')
                self.build_button.configure(state='normal' if self.workflow.inspection else 'disabled')
                if action=='enable':
                    ready=bool(self.workflow.inspection and self.workflow.output and self.workflow.manifest
                        and self.workflow.manifest['temporary_flag_needed'])
                    self.enable_button.configure(state='normal' if ready else 'disabled')
                    self.card_check.configure(state='normal' if ready else 'disabled')
                if kind=='error':
                    # Backend readiness is invalidated before a fresh read or
                    # replacement build. Do not leave the former instructions
                    # or controls looking ready after that operation fails.
                    if action in ('inspect','prepare'):
                        self.set_steps('Read the camera and prepare a verified update before installation.')
                        self.set_limitations([])
                    if action=='inspect':self.camera_text.set('Camera check did not complete. Reconnect an awake service camera and read it again.')
                    if action=='enable' and self.workflow.output:
                        self.open_button.configure(state='normal')
                    self.status.set('Stopped: '+result)
                    if action=='prepare' and self.source.get()=='download':
                        self.source.set('local')
                        result+='\n\nIf the download is unavailable, choose the official 1.1 BIN or ZIP for the detected model. Its hash must match.'
                    messagebox.showerror('Could not complete this step',result,parent=self.root)
                elif action=='inspect':
                    enabled=result['modified_updates_enabled']
                    _,self.catalog=catalog(self.assets,model=result['model'])
                    for i,key in enumerate(('stable','luts','restore')):
                        self.choice_buttons[i].configure(text=self.catalog['choices'][key]['label'])
                        self.choice_descriptions[i].configure(text=self.catalog['choices'][key]['description'])
                    self.download_text.set('Download the official '+model_spec(result['model'])['token']+' 1.1 firmware')
                    self.camera_text.set(result['model']+' — firmware '+result['firmware']+' (internal '+result['internal_revision']+')\n\n'+
                        ('This camera already accepts custom updates. No temporary USB change is needed.' if enabled else
                         'The update policy is stock. After preparing the card, reconnect service USB to enable this update.'))
                    self.open_button.configure(state='disabled');self.enable_button.configure(state='disabled')
                    self.card.set(False);self.set_steps('Choose a patch and prepare the firmware files.');self.set_limitations([])
                    self.status.set('Camera firmware checked');self.tabs.select(1)
                elif action=='prepare':
                    self.set_steps(self.workflow.instructions(result).split('\nLimitations:')[0])
                    self.set_limitations(result['candidate']['limitations']);self.card.set(False)
                    self.open_button.configure(state='normal')
                    self.enable_button.configure(state='normal' if result['temporary_flag_needed'] else 'disabled')
                    self.card_check.configure(state='normal' if result['temporary_flag_needed'] else 'disabled')
                    self.status.set('Verified files saved. Copy '+result['update_filename']+' to the SD card.');self.tabs.select(2)
                elif action=='enable':
                    self.open_button.configure(state='normal')
                    self.status.set('Update access verified. Keep the camera awake and powered on.')
                    self.set_steps('Update access is verified.\n\nUnplug USB without switching the camera off or letting it sleep. '
                        'Press Playback, then follow the update confirmation on the camera. Keep power stable until it finishes.\n\n'
                        'If the camera sleeps or restarts before installation, reconnect service USB and click Enable this update again. '
                        'The prepared firmware does not need to be rebuilt.\n\n'
                        'After restart, verify the installed firmware.\n\n'+STOCK_RESTORE_RESET)
                self.bar.configure(value=0)
        except queue.Empty:pass
        self.root.after(80,self.poll)

    def on_inspect(self):self.start('inspect',lambda p:self.workflow.inspect(p))

    def choose_file(self):
        path=filedialog.askopenfilename(parent=self.root,title='Official camera firmware',
            filetypes=[('Firmware BIN or ZIP','*.bin *.BIN *.zip *.ZIP'),('All files','*')])
        if path:self.local.set(path);self.source.set('local')

    def on_prepare(self):
        if self.source.get()=='local' and not self.local.get():self.choose_file()
        if self.source.get()=='local' and not self.local.get():return
        parent=filedialog.askdirectory(parent=self.root,title='Choose where to save the prepared firmware')
        if not parent:return
        choice=self.choice.get();local=self.local.get() if self.source.get()=='local' else None
        model=self.workflow.inspection.model
        destination=Path(parent)/(model_spec(model)['token']+'-'+choice+'-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        self.open_button.configure(state='disabled');self.enable_button.configure(state='disabled')
        self.start('prepare',lambda p:self.workflow.prepare(choice,destination,local_firmware=local,progress=p))

    def on_enable(self):
        if not self.card.get():
            messagebox.showinfo('Prepare the card first','Copy the update, insert the card with the camera OFF, then start service mode and reconnect USB.',parent=self.root)
            return
        self.start('enable',lambda p:self.workflow.enable(card_inserted_with_power_off=True,progress=p))

    def open_folder(self):
        if not self.workflow.output:return
        if sys.platform=='win32':
            import os
            os.startfile(str(self.workflow.output))
        else:subprocess.Popen(['open',str(self.workflow.output)])

    def connection_help(self):
        messagebox.showinfo('Connect service USB',
            'Use an awake GM1 or GM5 in service mode. Close other camera applications, and reconnect the cable if it has slept.\n\n'
            'Windows: the camera service interface must use WinUSB. Install it for the exact camera entry (USB ID04DA:2370), then retry. '
            'The updater does not install or change drivers.\n\n'
            'The initial camera check only reads firmware. A temporary RAM flag can be changed after the update is built and the card is prepared.',parent=self.root)

    def close(self):
        if self.busy=='enable':
            self.status.set('Finishing the camera flag check; keep USB connected.');return
        self.root.destroy()


def main(assets=None):
    root=tk.Tk();App(root,assets=assets);root.mainloop()


def smoke_report(path,assets=None):
    """Open the real desktop UI and inspect its initial state without USB."""
    import json
    class NoCameraWorkflow(Workflow):
        def inspect(self,*args,**kwargs):raise RuntimeError('Camera access is disabled in the GUI smoke check')
    root=tk.Tk();app=App(root,assets=assets,workflow=NoCameraWorkflow(assets=assets))
    results=[];errors=[]
    def check():
        try:
            for geometry in ('840x740','800x690'):
                root.geometry(geometry);root.update()
                for index,page in enumerate(app.pages):
                    app.tabs.select(index);root.update_idletasks()
                    result=dict(geometry=geometry,page=index,width=page.winfo_width(),
                        height=page.winfo_height(),needed_width=page.winfo_reqwidth(),
                        needed_height=page.winfo_reqheight())
                    results.append(result)
                    if result['width']<result['needed_width'] or result['height']<result['needed_height']:
                        errors.append('Page '+str(index)+' does not fit at '+geometry)
            states={name:str(widget.cget('state')) for name,widget in
                (('read',app.read_button),('prepare',app.build_button),('enable',app.enable_button))}
            if states!={'read':'normal','prepare':'disabled','enable':'disabled'}:
                errors.append('Initial camera-write controls are not disabled')
            report=dict(passed=not errors,tk_version=root.tk.call('info','patchlevel'),
                pages=results,initial_controls=states,errors=errors,camera_contacted=False)
            with Path(path).open('x',encoding='utf-8') as stream:
                stream.write(json.dumps(report,indent=2)+'\n')
        finally:root.destroy()
    root.after(600,check);root.mainloop()
    if errors:raise RuntimeError('; '.join(errors))
