"""Exercise production offline CTF actions; rendering/physics need the client.

Run: python3 -B -m unittest discover -s source/tests -p test_bot_ctf.py -v
"""
from pathlib import Path
import subprocess
import tempfile
import unittest


class BotCTFTest(unittest.TestCase):
    def compile_run(self, code):
        with tempfile.TemporaryDirectory(prefix="ac-ctf-test-") as directory:
            path = Path(directory)
            (path / "ctf.cpp").write_text(code)
            subprocess.run(["clang++", "-std=c++11", "-Wall", "-Wextra",
                            str(path / "ctf.cpp"), "-o", str(path / "ctf")], check=True)
            subprocess.run([str(path / "ctf")], check=True)

    def test_offline_flag_lifecycle(self):
        source = (Path(__file__).resolve().parents[1] / "src/entities.cpp").read_text()
        actions = source[source.index("static int botCTFDroppedAt"):source.index("void trypickupflag(")]
        fixture = r'''
#include <cassert>
#include <cstddef>
#define loopi(n) for(int i=0; i<(n); ++i)
#define OUTBORD(x,y) ((x)<1 || (y)<1 || (x)>126 || (y)>126)
enum { CS_ALIVE, CS_DEAD, CTFF_INBASE, CTFF_STOLEN, CTFF_DROPPED,
       FM_PICKUP, FM_DROP, FM_LOST, FM_RETURN, FM_SCORE, FM_RESET };
struct vec { float x,y,z; vec(float x=0,float y=0,float z=0):x(x),y(y),z(z) {} };
struct entity { int x=20,y=40; bool spawned=true; } bases[2];
struct playerent { int clientnum=1,team=0,state=CS_ALIVE,flagscore=0; vec o=vec(40,40,4.5); };
struct flaginfo {
    int state=CTFF_INBASE,actor_cn=-1;
    playerent *actor=nullptr;
    entity *flagent=nullptr;
    bool ack=true;
    vec pos;
} flaginfos[2];
bool m_botctf=true,intermission=false,ispaused=false,needscoresreorder=false;
int lastmillis=100, messages[32]={0};
bool team_isactive(int t) { return t==0 || t==1; }
int team_base(int t) { return t&1; }
void flagmsg(int,int message,int,int) { ++messages[message]; }
void flaginbase(int flag) {
    auto &f=flaginfos[flag]; f.actor=nullptr; f.actor_cn=-1;
    f.pos=vec(f.flagent->x,f.flagent->y,0); f.flagent->spawned=true; f.ack=true;
}
// The fixture models a successful physics drop. The full client supplies the
// real gravity/collision implementation of flagdropped().
void flagdropped(int flag,float x,float y,float) {
    flaginfos[flag].pos=vec(x,y,0); flaginfos[flag].ack=true;
}
void dropbotctfflags(playerent *, bool manual=false);
'''
        scenarios = r'''
int main() {
    playerent human, ally, enemy; ally.clientnum=2; enemy.clientnum=3; enemy.team=1;
    bases[1].x=100;
    for(int i=0;i<2;++i) { flaginfos[i].flagent=&bases[i]; flaginbase(i); }
    resetbotctf();
    bases[1].spawned=false; updatebotctf(); assert(bases[1].spawned);
    touchbotctfflag(1,&ally);
    assert(flaginfos[1].state==CTFF_STOLEN && flaginfos[1].actor==&ally);
    assert(!bases[1].spawned && flaginfos[1].ack);
    updatebotctf(); assert(!bases[1].spawned);
    touchbotctfflag(1,&human); assert(flaginfos[1].actor==&ally);
    touchbotctfflag(0,&ally);
    assert(ally.flagscore==1 && flaginfos[1].state==CTFF_INBASE && bases[1].spawned);
    assert(messages[FM_SCORE]==1 && needscoresreorder);
    // A player can also steal, manually drop and pick up after the cooldown.
    touchbotctfflag(1,&human); dropbotctfflags(&human,true);
    assert(flaginfos[1].state==CTFF_DROPPED && !flaginfos[1].actor);
    touchbotctfflag(1,&human); assert(flaginfos[1].state==CTFF_DROPPED);
    lastmillis+=3000; touchbotctfflag(1,&human);
    assert(flaginfos[1].actor==&human);
    // Both flags stolen: reaching home cannot score until our flag is back.
    touchbotctfflag(0,&enemy); touchbotctfflag(0,&human);
    assert(human.flagscore==0 && flaginfos[1].actor==&human);
    enemy.state=CS_DEAD; updatebotctf();
    assert(flaginfos[0].state==CTFF_DROPPED && flaginfos[0].actor==nullptr);
    touchbotctfflag(0,&ally); assert(flaginfos[0].state==CTFF_INBASE);
    touchbotctfflag(0,&human); assert(human.flagscore==1);
    // Death/suicide is a drop; enemy recovery returns that flag to its base.
    touchbotctfflag(1,&ally); ally.state=CS_DEAD; updatebotctf();
    assert(flaginfos[1].state==CTFF_DROPPED);
    enemy.state=CS_ALIVE; touchbotctfflag(1,&enemy);
    assert(flaginfos[1].state==CTFF_INBASE);
    // Forgotten flags reset after 30 seconds, never while paused/intermission.
    ally.state=CS_ALIVE; touchbotctfflag(1,&ally); dropbotctfflags(&ally);
    lastmillis+=29999; updatebotctf(); assert(flaginfos[1].state==CTFF_DROPPED);
    ++lastmillis; ispaused=true; updatebotctf(); assert(flaginfos[1].state==CTFF_DROPPED);
    ispaused=false; updatebotctf(); assert(flaginfos[1].state==CTFF_INBASE);
    intermission=true; touchbotctfflag(1,&human); assert(flaginfos[1].state==CTFF_INBASE);
    intermission=false;
    // Changing team, becoming a spectator, removing a carrier, or leaving the
    // map cannot leave the flag attached to a stale or friendly carrier.
    touchbotctfflag(1,&ally); ally.team=1; updatebotctf();
    assert(flaginfos[1].state==CTFF_DROPPED && !flaginfos[1].actor);
    botctfbase(1); ally.team=0; touchbotctfflag(1,&ally); ally.team=2; updatebotctf();
    assert(flaginfos[1].state==CTFF_DROPPED);
    botctfbase(1); touchbotctfflag(1,&human); dropbotctfflags(&human);
    assert(flaginfos[1].actor==nullptr);
    lastmillis+=3000; touchbotctfflag(1,&human); human.o.x=-10; dropbotctfflags(&human);
    assert(flaginfos[1].state==CTFF_INBASE);
    // No offline behavior is applied to normal network CTF.
    m_botctf=false; touchbotctfflag(1,&human); assert(flaginfos[1].state==CTFF_INBASE);
}
'''
        self.compile_run(fixture + actions + scenarios)

    def test_mode_masks(self):
        source = (Path(__file__).resolve().parents[1] / "src/protocol.h").read_text()
        modes = source[source.index("enum\n{\n    GMODE_DEMO"):source.index("// single filter modes")]
        self.compile_run('#include <cassert>\n' + modes + r'''
int main() {
    int gamemode=GMODE_BOTCTF;
    assert(GMODE_BOTCTF==22 && GMODE_CTF==5 && GMODE_BOTTEAMDEATHMATCH==7);
    assert(m_botctf && m_botmode && m_ctf && m_flags_ && m_teammode);
    assert(!m_mp(gamemode) && !m_arena);
    assert((GMMASK__BOT & GMMASK_BOTCTF) && (GMMASK__FLAGS & GMMASK_BOTCTF));
    assert((GMMASK__TEAMSPAWN & GMMASK_BOTCTF) && !(GMMASK__MP & GMMASK_BOTCTF));
    gamemode=GMODE_CTF; assert(!m_botctf && !m_botmode && m_ctf && m_mp(gamemode));
    gamemode=GMODE_BOTTEAMDEATHMATCH; assert(m_botmode && !m_flags_ && !m_mp(gamemode));
}
''')


if __name__ == "__main__":
    unittest.main()
