"""Compile the production squad policy/coordinator against a navigation fixture.

This verifies orders, role allocation and leapfrog transitions, not engine physics.
Run: python3 -B -m unittest discover -s source/tests -p test_bot_squad.py -v
"""
from pathlib import Path
import subprocess
import tempfile
import unittest


class BotSquadTest(unittest.TestCase):
    def test_navigation_and_independent_aim(self):
        source = (Path(__file__).resolve().parents[1] / "src/bot/bot_ai.cpp").read_text()
        navigation = source[source.index("void CBot::NavigateSquad("):source.index("bool CBot::DoSquadAI()")]
        fixture = r'''
#include <cassert>
#include <cmath>
#define RAD (3.14159265358979323846f/180)
struct vec {
    float x,y,z;
    vec(float x=0,float y=0,float z=0):x(x),y(y),z(z) {}
    void sub(const vec &b) { x-=b.x;y-=b.y;z-=b.z; }
    float magnitudexy() const { return sqrtf(x*x+y*y); }
    void normalize() { float n=magnitudexy(); x/=n;y/=n; }
};
struct Node { vec v_origin; } fromNode,toNode,pathNode;
struct waypoint_s { Node *pNode; } fromWP{&fromNode},toWP{&toNode},pathWP{&pathNode};
struct botent { vec o; float yaw=90,targetyaw=77,targetpitch=15; int move=0,strafe=0; } bot;
bool m_botctf=true; int lastmillis=100;
struct CBot {
    botent *m_pMyEnt=&bot;
    vec m_vSquadGoal,m_vGoal,m_vSquadFacing;
    waypoint_s *m_pCurrentWaypoint=nullptr,*m_pCurrentGoalWaypoint=nullptr;
    int m_iSquadRepath=0;
    bool direct=false,route=true,calculating=false;
    void NavigateSquad(bool combat);
    void ResetMoveSpeed() { bot.move=bot.strafe=0; }
    void ResetWaypointVars() { m_pCurrentWaypoint=m_pCurrentGoalWaypoint=nullptr; }
    void AimToVec(vec) { bot.targetyaw=120;bot.targetpitch=0; }
    float GetDistance(vec v) { v.sub(bot.o);return sqrtf(v.x*v.x+v.y*v.y+v.z*v.z); }
    bool IsReachable(vec,float) { return direct; }
    waypoint_s *GetNearestWaypoint(float) { return &fromWP; }
    waypoint_s *GetNearestWaypoint(vec,float) { return &toWP; }
    void SetCurrentWaypoint(waypoint_s *p) { m_pCurrentWaypoint=p; }
    void SetCurrentGoalWaypoint(waypoint_s *p) { m_pCurrentGoalWaypoint=p; }
    bool HeadToGoal() {
        assert(bot.move==1); // inherited navigation requires this input
        m_pCurrentWaypoint=&pathWP;
        if(calculating) ResetMoveSpeed();
        return route;
    }
    void CheckJump() {}
};
'''
        scenarios = r'''
int main() {
    CBot ai; ai.m_vSquadGoal=vec(20,0,0); pathNode.v_origin=vec(0,10,0);
    ai.NavigateSquad(true);
    // Move along the path while continuing to aim at the enemy.
    assert(bot.move==0 && bot.strafe==-1 && bot.targetyaw==77 && bot.targetpitch==15);
    ai.calculating=true; ai.NavigateSquad(true);
    assert(bot.move==0 && bot.strafe==0);
    ai.calculating=false; ai.route=false; ai.NavigateSquad(true);
    assert(bot.move==0 && bot.strafe==0);
    ai.direct=true; ai.NavigateSquad(true);
    assert(bot.move==1 && bot.strafe==0 && bot.targetyaw==77 && bot.targetpitch==15);
    // CTF needs to approach inside the actual pickup radius of 2.5 cubes.
    bot.o=vec(18,0,0); ai.NavigateSquad(false); assert(bot.move==1);
    bot.o=vec(19,0,0); ai.NavigateSquad(false); assert(bot.move==0 && bot.strafe==0);
}
'''
        with tempfile.TemporaryDirectory(prefix="ac-squad-nav-") as directory:
            path = Path(directory)
            (path / "nav.cpp").write_text(fixture + navigation + scenarios)
            subprocess.run(["clang++", "-std=c++11", "-Wall", "-Wextra",
                            str(path / "nav.cpp"), "-o", str(path / "nav")], check=True)
            subprocess.run([str(path / "nav")], check=True)

    def test_coordination(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "src/bot/bot_ai.cpp").read_text()
        coordinator = source[source.index("struct BotSquad\n"):source.index("void CBot::NavigateSquad(")]
        squad_ai = source[source.index("bool CBot::DoSquadAI()"):source.index("void CBot::MainAI()")]
        fixture = r'''
#include <cassert>
#include <cmath>
#include <cstring>
#include <map>
#include <queue>
#include <vector>
#include "bot_squad.h"
template<class T> struct vector : std::vector<T> {
    int length() const { return int(this->size()); }
    void add(T value) { this->push_back(value); }
};
#define loopi(n) for(int i=0; i<(n); ++i)
#define loopj(n) for(int j=0; j<(n); ++j)
#define loopv(v) for(int i=0; i<(v).length(); ++i)
#define loopvj(v) for(int j=0; j<(v).length(); ++j)
#define COMMAND(name, args)
#define OUTBORD(x,y) ((x)<1 || (y)<1 || (x)>126 || (y)>126)
#define SOLID(s) ((s)->solid)
struct vec {
    float x=0, y=0, z=0;
    vec() {}
    vec(float x,float y,float z):x(x),y(y),z(z) {}
    float dist(const vec &b) const { return sqrtf((x-b.x)*(x-b.x)+(y-b.y)*(y-b.y)+(z-b.z)*(z-b.z)); }
};
template<class T> struct TLinkedList {
    struct node_s { T Entry; node_s *next; };
    node_s *first=nullptr;
    ~TLinkedList() { while(first) { auto n=first; first=n->next; delete n; } }
    node_s *GetFirst() { return first; }
    void add(T value) { first=new node_s{value,first}; }
};
struct node_s { vec v_origin; TLinkedList<node_s *> ConnectedWPs; };
struct Square { int floor=0; bool solid=false; } square;
Square *S(int,int) { return &square; }
struct botent;
enum { STATE_NORMAL, STATE_ENT, STATE_SQUAD };
struct CBot {
    botent *m_pMyEnt=nullptr;
    int m_eCurrentBotState=STATE_NORMAL;
    int weaponChoices=0,shots=0;
    bool items=false, navigated=false;
    bool DoSquadAI();
    bool FindEnemy();
    void ChoosePreferredWeapon();
    void CheckReload() {}
    void CheckScope() {}
    bool CheckItems() { return items; }
    void ShootEnemy();
    void NavigateSquad(bool) { navigated=true; }
    bool m_bSquadTask=false;
    botsquad::Role m_eSquadRole=botsquad::ASSAULT;
    botsquad::CTFTask m_eCTFTask=botsquad::NO_FLAG_TASK;
    int m_iCTFGoalUpdate=0;
    bool visible=true;
    template<class T> bool IsVisible(T *) { return visible; }
    template<class T> bool IsInFOV(T *) { return visible; }
    bool IsReachable(vec, float) { return true; }
    int m_iFireteam=0, m_iSquadRepath=0, resets=0;
    void *m_pTargetEnt=nullptr;
    vec m_vSquadGoal, m_vSquadFacing;
    void ResetWaypointVars() { ++resets; }
};
enum { CS_ALIVE, CS_DEAD, CTF_FLAG, PLAYERSTART, CTFF_INBASE, CTFF_STOLEN, CTFF_DROPPED };
struct Weapon { int reloading=0; } weapons[3];
struct botent {
    int team=0, clientnum=0, state=CS_ALIVE, health=100, gunselect=0, mag[1]={10};
    float eyeheight=4.5f;
    vec o;
    const char *name="bot";
    Weapon *weaponsel=nullptr;
    CBot *pBot=nullptr;
    int primary=0,ammo[1]={10};
    botent *enemy=nullptr;
};
bool CBot::FindEnemy() { return m_pMyEnt->enemy!=nullptr; }
void CBot::ChoosePreferredWeapon() { assert(m_pMyEnt->enemy); ++weaponChoices; }
void CBot::ShootEnemy() { assert(m_pMyEnt->enemy); ++shots; }
struct Manager { bool BotsShoot() { return true; } } BotManager;
struct Entity { int type, attr2, x, y; };
struct flaginfo { int state=CTFF_INBASE; botent *actor=nullptr; vec pos; } flaginfos[2];
vector<botent *> bots;
vector<Entity> ents;
botent human, *player1=&human;
// Match the engine's legacy placeholder: it is a mode ID, not a boolean.
#define m_classicsp 1000
bool m_botmode=true, m_teammode=true, m_botctf=false;
int botsquads=1, lastmillis=100;
bool team_isactive(int t) { return t==0 || t==1; }
int team_base(int t) { return t; }
template<class... T> void conoutf(const char *, T...) {}
struct Navigation {
    vector<node_s *> nodes;
    node_s *GetNearestWaypoint(vec goal, float range) {
        node_s *best=nullptr;
        for(auto n:nodes) if(n->v_origin.dist(goal)<range) {
            range=n->v_origin.dist(goal); best=n;
        }
        return best;
    }
} WaypointClass;
'''
        scenarios = r'''
int main() {
    using namespace botsquad;
    assert(guards(3,BALANCED)==1 && guards(4,BALANCED)==2);
    assert(guards(1,BALANCED)==0 && guards(2,BALANCED)==0);
    assert(guards(4,ATTACK)==0 && guards(4,DEFEND)==4);
    assert(transition(100,1,1,true,true)==WAIT);
    assert(transition(1500,1,1,false,true)==WAIT);
    assert(transition(1500,1,1,true,false)==WAIT);
    assert(transition(1500,1,1,true,true)==ADVANCE);
    assert(transition(12000,1,1,false,true)==REGROUP);
    assert(transition(1500,1,0,false,false)==SOLO);

    node_s nodes[8];
    vec points[]={vec(20,40,4.5),vec(20,52,4.5),vec(32,52,4.5),vec(44,52,4.5),
                  vec(56,52,4.5),vec(68,52,4.5),vec(80,52,4.5),vec(80,40,4.5)};
    for(int i=0;i<8;++i) {
        // Real flood nodes use floor+2, below the player's eye position.
        nodes[i].v_origin=vec(points[i].x,points[i].y,2); WaypointClass.nodes.add(&nodes[i]);
        if(i) { nodes[i-1].ConnectedWPs.add(&nodes[i]); nodes[i].ConnectedWPs.add(&nodes[i-1]); }
    }
    ents.add({CTF_FLAG,0,20,40}); ents.add({CTF_FLAG,1,80,40});
    // The bound follows the detour, rather than the straight line to the enemy.
    assert(SquadBound(points[0],points[7]).dist(points[1])<0.01f);
    assert(SquadBound(points[7],points[0]).dist(points[6])<0.01f);
    // Disconnected goals are never treated as reached or advanced past.
    node_s isolated; isolated.v_origin=vec(110,110,4.5);
    WaypointClass.nodes.add(&isolated);
    assert(SquadBound(points[0],isolated.v_origin).dist(points[0])<0.01f);

    botent members[3]; CBot ai[3];
    for(int i=0;i<3;++i) {
        members[i].pBot=&ai[i]; members[i].clientnum=i+1;
        ai[i].m_pMyEnt=&members[i];
        members[i].o=points[0]; members[i].weaponsel=&weapons[i]; bots.add(&members[i]);
    }
    UpdateBotSquads();
    assert(ai[0].m_eSquadRole==GUARD);
    assert(ai[1].m_iFireteam==0 && ai[2].m_iFireteam==1);
    assert(ai[1].m_vSquadGoal.dist(points[1])<0.01f);
    assert(ai[2].m_vSquadGoal.dist(points[0])<0.01f);
    // Weapon selection requires an enemy; routine mission movement must not
    // dereference the null enemy pointer used outside combat.
    assert(ai[1].DoSquadAI() && ai[1].weaponChoices==0 && ai[1].navigated);
    botent target; target.team=1; ai[1].m_pMyEnt->enemy=&target;
    assert(ai[1].DoSquadAI() && ai[1].weaponChoices==1 && ai[1].shots==1);
    ai[1].m_pMyEnt->enemy=nullptr;
    // Arrival switches the moving group and leapfrogs beyond the first group.
    members[1].o=ai[1].m_vSquadGoal; lastmillis=1600;
    UpdateBotSquads();
    assert(botSquads[0].moving==1 && ai[2].m_vSquadGoal.dist(points[2])<0.01f);
    // A reloading or distant support group does not release the next bound.
    members[2].o=ai[2].m_vSquadGoal; weapons[1].reloading=1; lastmillis=3200;
    UpdateBotSquads(); assert(botSquads[0].moving==1);
    weapons[1].reloading=0; members[1].o=points[0];
    UpdateBotSquads(); assert(botSquads[0].moving==1);
    // Timeout regroups using current positions rather than pretending arrival.
    lastmillis=14000; UpdateBotSquads();
    assert(botSquads[0].started==lastmillis);
    assert(ai[2].m_vSquadGoal.dist(members[2].o)<0.01f);
    // Losing an entire fireteam releases the survivor, without a deadlock.
    members[1].state=CS_DEAD; UpdateBotSquads();
    assert(ai[2].m_vSquadGoal.dist(points[7])<0.01f);
    members[1].state=CS_ALIVE;
    // Orders are restricted to the selected team, and can be changed in place.
    char defend[]="defend"; botsquadorder(defend); UpdateBotSquads();
    for(auto &a:ai) assert(a.m_eSquadRole==GUARD);
    assert(botSquads[1].strategy==BALANCED);
    botsquadstatus();
    char attack[]="attack";
    human.team=2; botsquadorder(attack);
    assert(botSquads[0].strategy==DEFEND);
    human.team=0;
    assert(!SetBotSquadOrder(-1,ATTACK));
    assert(!SetBotSquadOrder(2,ATTACK));
    SetBotSquadOrder(0,ATTACK); UpdateBotSquads();
    for(auto &a:ai) assert(a.m_eSquadRole==ASSAULT);
    // CTF role objectives override patrol/bounding goals immediately.
    m_botctf=true; SetBotSquadOrder(0,BALANCED); UpdateBotSquads();
    assert(ai[0].m_eSquadRole==GUARD && ai[1].m_eCTFTask==STEAL_FLAG);
    flaginfos[1].state=CTFF_STOLEN; flaginfos[1].actor=&members[1];
    UpdateBotSquads();
    assert(ai[1].m_eCTFTask==RETURN_FLAG && ai[1].m_vSquadGoal.dist(points[0])<0.01f);
    ai[1].m_pMyEnt->health=20; ai[1].items=true;
    assert(ai[1].DoSquadAI() && ai[1].m_eCurrentBotState==STATE_SQUAD);
    ai[1].m_pMyEnt->health=100; ai[1].items=false;
    assert(ai[2].m_eCTFTask==ESCORT_FLAG);
    flaginfos[0].state=CTFF_DROPPED; flaginfos[0].pos=vec(44,52,0);
    UpdateBotSquads();
    assert(ai[0].m_eCTFTask==RECOVER_FLAG && ai[0].m_vSquadGoal.dist(points[3])<0.01f);
    botent thief; thief.team=1; thief.o=points[4];
    flaginfos[0].state=CTFF_STOLEN; flaginfos[0].actor=&thief;
    ai[0].visible=false; UpdateBotSquads();
    assert(ai[0].m_eCTFTask==NO_FLAG_TASK);
    ai[0].visible=true; UpdateBotSquads();
    assert(ai[0].m_eCTFTask==INTERCEPT_FLAG && ai[0].m_vSquadGoal.dist(thief.o)<0.01f);
    // Even a guard who picks up the enemy flag must bring it home.
    flaginfos[1].actor=&members[0]; UpdateBotSquads();
    assert(ai[0].m_eCTFTask==RETURN_FLAG);
    flaginfos[0].state=flaginfos[1].state=CTFF_INBASE;
    flaginfos[0].actor=flaginfos[1].actor=nullptr;
    botsquads=0; lastmillis+=1000; UpdateBotSquads();
    assert(ai[1].m_bSquadTask && ai[1].m_eCTFTask==STEAL_FLAG);
    assert(ai[1].m_vSquadGoal.dist(points[7])<0.01f);
    botsquads=1; m_botctf=false;
    // Roster changes replan; death alone does not renumber the roster.
    auto roster=botSquads[0].roster; bots.pop_back(); UpdateBotSquads();
    assert(botSquads[0].roster!=roster);
    m_teammode=false; UpdateBotSquads();
    assert(!ai[0].m_bSquadTask && !ai[1].m_bSquadTask);
    m_teammode=true; botsquads=0; UpdateBotSquads(); assert(!ai[0].m_bSquadTask);
    botsquads=1; ents.clear(); UpdateBotSquads(); assert(!ai[0].m_bSquadTask);
    ResetBotSquads(); assert(!botSquads[0].initialized && botSquads[0].strategy==BALANCED);
}
'''
        with tempfile.TemporaryDirectory(prefix="ac-squad-test-") as directory:
            path = Path(directory)
            (path / "squad.cpp").write_text(fixture + coordinator + squad_ai + scenarios)
            subprocess.run(["clang++", "-std=c++11", "-Wall", "-Wextra",
                            "-I", str(root / "src/bot"), str(path / "squad.cpp"),
                            "-o", str(path / "squad")], check=True)
            subprocess.run([str(path / "squad")], check=True)


if __name__ == "__main__":
    unittest.main()
