import os
from pathlib import Path
import sqlite3
import sys
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import launcher_hosts as hosts


class Process:
    def __init__(self, pid, cwd, args, name='python.exe', parents=(), children=()):
        self.pid, self.directory, self.args, self.executable = pid, str(cwd), args, name
        self.ancestors, self.descendants = list(parents), list(children)
        self.terminated = self.killed = False

    def cwd(self): return self.directory
    def cmdline(self): return self.args
    def name(self): return self.executable
    def parents(self): return self.ancestors
    def children(self, recursive=False): return self.descendants
    def terminate(self): self.terminated = True
    def kill(self): self.killed = True


def connection(port, pid):
    return SimpleNamespace(status=psutil.CONN_LISTEN, laddr=SimpleNamespace(port=port), pid=pid)


def test_intentional_restart_marks_only_valid_launch_ids(tmp_path):
    valid = Mock(environ=Mock(return_value={'DEEPSTEM_LAUNCH_ID':'123-456-789'}))
    invalid = Mock(environ=Mock(return_value={'DEEPSTEM_LAUNCH_ID':'../../outside'}))
    hosts.mark_intentional_restart(tmp_path, [valid, invalid])
    assert (tmp_path/'data-private'/'restart-123-456-789.flag').is_file()
    assert len(list((tmp_path/'data-private').iterdir())) == 1


def test_orphaned_tunnel_is_owned_only_by_exact_config_and_target(tmp_path):
    config = str(tmp_path/'data-private'/'online-cloudflare.yml')
    ours = Process(90100,tmp_path,['cloudflared','tunnel','--config',config,'--url','http://127.0.0.1:8080'],name='cloudflared.exe')
    other = Process(90101,tmp_path,['cloudflared','tunnel','--config',str(tmp_path/'other.yml'),'--url','http://127.0.0.1:8080'],name='cloudflared.exe')
    new = Process(90102,tmp_path,ours.args,name='cloudflared.exe',parents=[SimpleNamespace(pid=os.getpid())])
    assert hosts.owned_tunnels(tmp_path,[ours,other,new]) == [ours]


def test_stopped_online_status_removes_stale_organizer_link(tmp_path):
    import json
    (tmp_path/'artifacts').mkdir()
    (tmp_path/'data-private').mkdir()
    status = tmp_path/'artifacts'/'online-status.json'
    status.write_text(json.dumps({'status':'ready','app_url':'https://old.example.org'}))
    access = tmp_path/'data-private'/'online-access.html'
    access.write_text('<a href="https://old.example.org/#event-organizer=private">Old login</a>')
    hosts.invalidate_online_access(tmp_path)
    assert json.loads(status.read_text())['status'] == 'stopped'
    assert 'Online access is stopped' in access.read_text()
    assert 'event-organizer=' not in access.read_text()


@pytest.mark.skipif(os.name != 'nt', reason='Windows launcher behavior')
@pytest.mark.parametrize('case,expected_code', [('success',0),('restart',0),('failure',1)])
def test_cmd_distinguishes_restart_from_actual_failure(tmp_path, case, expected_code):
    root = tmp_path/'studio with spaces'
    (root/'.venv'/'Scripts').mkdir(parents=True)
    (root/'scripts').mkdir()
    shutil.copy2(sys.executable, root/'.venv'/'Scripts'/'python.exe')
    (root/'.venv'/'pyvenv.cfg').write_text(f'home = {Path(sys._base_executable).parent}\ninclude-system-site-packages = false\n')
    shutil.copy2(Path(__file__).resolve().parents[2]/'Start Studio.cmd', root/'Start Studio.cmd')
    (root/'scripts'/'launch.py').write_text(
        "import os,pathlib,sys\n"
        "print('Studio is ready.')\n"
        "case=os.environ['LAUNCHER_TEST_CASE']\n"
        "if case=='restart':\n"
        " p=pathlib.Path('data-private')/('restart-'+os.environ['DEEPSTEM_LAUNCH_ID']+'.flag')\n"
        " p.parent.mkdir(exist_ok=True);p.write_text('restart')\n"
        "sys.exit(0 if case=='success' else 1)\n")
    result = subprocess.run(f'cmd.exe /d /c ""{root / "Start Studio.cmd"}" --no-browser"',
        cwd=root, env={**os.environ,'LAUNCHER_TEST_CASE':case}, input='\n',
        capture_output=True,text=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == expected_code, result.stdout+result.stderr
    assert ('replaced by another launcher' in result.stdout) == (case=='restart')
    assert ('Studio stopped with exit code 1' in result.stdout) == (case=='failure')


def studio(root):
    supervisor=Process(90000,root,['python','scripts/launch.py'])
    api=Process(90001,root,['python','-m','uvicorn','app.main:create_app'],parents=[supervisor])
    preview=Process(90002,root,['python','-m','uvicorn','app.preview:create_preview'],parents=[supervisor])
    frontend=Process(90003,root/'frontend',['node',str(root/'frontend/node_modules/vite/bin/vite.js')],name='node.exe',parents=[supervisor])
    processes={p.pid:p for p in [supervisor,api,preview,frontend]}
    sockets=[connection(8000,api.pid),connection(8001,preview.pid),connection(5173,frontend.pid)]
    return processes,sockets


def test_identifies_only_services_from_this_checkout_and_their_old_supervisor(tmp_path):
    processes,sockets=studio(tmp_path)
    sockets.append(sockets[0])  # IPv4/IPv6 listeners for one process are deduplicated.
    owned,supervisors,ports=hosts.find_hosts(tmp_path,sockets,processes.__getitem__)
    assert {p.pid for p in owned}=={90001,90002,90003}
    assert [p.pid for p in supervisors]==[90000]
    assert ports=={5173,8000,8001}
    assert not any(p.terminated for p in processes.values())


def test_refuses_another_checkouts_service_on_a_studio_port(tmp_path):
    other=tmp_path.parent/'different-checkout'
    process=Process(90001,other,['python','-m','uvicorn','app.main:create_app'])
    with pytest.raises(RuntimeError,match='another application'):
        hosts.find_hosts(tmp_path,[connection(8000,process.pid)],lambda _:process)
    assert not process.terminated


def test_foreign_launcher_with_same_filename_is_not_stopped(tmp_path):
    other=tmp_path.parent/'other-project'/'scripts'/'launch.py'
    supervisor=Process(90000,tmp_path,['python',str(other)])
    process=Process(90001,tmp_path,['python','-m','uvicorn','app.main:create_app'],parents=[supervisor])
    _,supervisors,_=hosts.find_hosts(tmp_path,[connection(8000,90001)],lambda _:process)
    assert supervisors==[]


def test_cannot_identify_port_owner_is_fail_closed(tmp_path):
    with pytest.raises(RuntimeError,match='Cannot identify'):
        hosts.find_hosts(tmp_path,[connection(8000,None)])
    with pytest.raises(RuntimeError,match='Cannot verify'):
        hosts.find_hosts(tmp_path,[connection(8000,90001)],Mock(side_effect=psutil.AccessDenied(90001)))


def test_preflights_all_ports_before_stopping_any_service(tmp_path,monkeypatch):
    processes,sockets=studio(tmp_path)
    foreign=Process(90004,tmp_path,['node','unrelated-server.js'],name='node.exe')
    processes[foreign.pid]=foreign
    sockets[-1]=connection(5173,foreign.pid)
    monkeypatch.setattr(hosts.psutil,'net_connections',lambda **_:sockets)
    monkeypatch.setattr(hosts.psutil,'Process',processes.__getitem__)
    stop=Mock();monkeypatch.setattr(hosts,'stop_processes',stop)
    with pytest.raises(RuntimeError,match='another application'):
        hosts.close_existing_hosts(tmp_path,'sqlite:///unused.db')
    stop.assert_not_called()


def database(tmp_path, active=False):
    path=tmp_path/'studio.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE generations (status TEXT)')
        if active:db.execute("INSERT INTO generations VALUES ('running')")
    return path, 'sqlite:///'+path.as_posix()


def test_active_generation_preserves_all_existing_hosts(tmp_path,monkeypatch):
    _,url=database(tmp_path,True)
    processes,sockets=studio(tmp_path)
    monkeypatch.setattr(hosts,'find_hosts',lambda _:(list(processes.values())[1:],[processes[90000]],{5173,8000,8001}))
    stop=Mock();monkeypatch.setattr(hosts,'stop_processes',stop)
    with pytest.raises(RuntimeError,match='still generating'):
        hosts.close_existing_hosts(tmp_path,url)
    stop.assert_not_called()


def test_generation_lock_prevents_new_reservations_until_shutdown_finishes(tmp_path):
    path,url=database(tmp_path)
    with hosts.generation_guard(url):
        with sqlite3.connect(path,timeout=.01) as second:
            with pytest.raises(sqlite3.OperationalError,match='locked'):
                second.execute("INSERT INTO generations VALUES ('running')")
    with sqlite3.connect(path) as second:
        second.execute("INSERT INTO generations VALUES ('running')")


def test_restart_stops_supervisor_first_and_waits_for_ports(tmp_path,monkeypatch):
    _,url=database(tmp_path)
    processes,_=studio(tmp_path)
    old=[processes[90001],processes[90002],processes[90003]]
    monkeypatch.setattr(hosts,'find_hosts',lambda _:(old,[processes[90000]],{5173,8000,8001}))
    stop=Mock();monkeypatch.setattr(hosts,'stop_processes',stop)
    monkeypatch.setattr(hosts.psutil,'net_connections',lambda **_:[])
    assert hosts.close_existing_hosts(tmp_path,url)==3
    assert stop.call_args_list[0].args[0]==[processes[90000]]
    assert stop.call_args_list[0].kwargs=={'include_children':False}
    assert stop.call_args_list[1].args[0]==old


def test_missing_database_refuses_to_stop_a_running_api(tmp_path):
    with pytest.raises(RuntimeError,match='Cannot locate'):
        with hosts.generation_guard('sqlite:///'+(tmp_path/'missing.db').as_posix()):
            pytest.fail('Guard must not allow shutdown')
    assert not (tmp_path/'missing.db').exists()


def test_crashed_api_reservations_do_not_prevent_frontend_only_replacement(tmp_path,monkeypatch):
    _,url=database(tmp_path,True)
    process=Process(90003,tmp_path,['node','vite'],name='node.exe')
    monkeypatch.setattr(hosts,'find_hosts',lambda _:([process],[],{5173}))
    stop=Mock();monkeypatch.setattr(hosts,'stop_processes',stop)
    monkeypatch.setattr(hosts.psutil,'net_connections',lambda **_:[])
    assert hosts.close_existing_hosts(tmp_path,url)==1
    with sqlite3.connect(tmp_path/'studio.db') as db:
        assert db.execute('SELECT status FROM generations').fetchone()[0]=='running'


def test_cleanup_stops_service_children_but_keeps_browser_windows(tmp_path,monkeypatch):
    node=Process(90002,tmp_path,['node','vite'],name='node.exe')
    browser=Process(90003,tmp_path,['chrome','http://localhost:5173'],name='chrome.exe')
    root=Process(90001,tmp_path,['cmd.exe','npm run dev'],name='cmd.exe',children=[node,browser])
    monkeypatch.setattr(hosts.psutil,'wait_procs',lambda processes,timeout:(processes,[]))
    hosts.stop_processes([root])
    assert root.terminated and node.terminated and not browser.terminated


def test_concurrent_startup_lock_is_released_for_next_launch(tmp_path):
    with hosts.startup_lock(tmp_path):
        with pytest.raises(RuntimeError,match='already in progress'):
            with hosts.startup_lock(tmp_path):pytest.fail('Second startup must not enter')
    with hosts.startup_lock(tmp_path):pass
