"""Exercise the production avoidance code with a small collision-world fixture.

Run with: python3 source/tests/test_bot_avoidance.py
Requires a C++ compiler. The fixture models player footprints, walls and ledges;
it does not replace an in-game check of the engine's map collision handling.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest


class BotAvoidanceTest(unittest.TestCase):
    def test_navigation_scenarios(self):
        source = (Path(__file__).resolve().parents[1] / "src/bot/bot_ai.cpp").read_text()
        avoidance = source[source.index("static vec BotMoveVector("):source.index("void CBot::DoCombatNav()")]
        fixture = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <vector>
using std::min;
using std::max;
#define RAD (3.14159265358979323846f/180)
#define loopv(v) for (int i = 0; i < int((v).size()); ++i)
enum { CS_ALIVE, CS_DEAD, ENT_PLAYER, ENT_BOT };
struct vec {
    float x, y, z;
    vec(float x=0, float y=0, float z=0): x(x), y(y), z(z) {}
    void sub(const vec &b) { x-=b.x; y-=b.y; z-=b.z; }
    float dot(const vec &b) const { return x*b.x+y*b.y+z*b.z; }
    float magnitudexy() const { return sqrtf(x*x+y*y); }
    float dist(const vec &b) const { vec d(*this); d.sub(b); return sqrtf(d.dot(d)); }
    void normalize() { float n=sqrtf(dot(*this)); x/=n; y/=n; z/=n; }
};
struct playerent {
    vec o, vel;
    float radius=1.1f, eyeheight=4.5f, aboveeye=0.7f, yaw=0;
    bool cancollide=true, onfloor=true, jumpnext=false;
    int state=CS_ALIVE, type=ENT_BOT, clientnum=0, move=1, strafe=0;
};
typedef playerent botent;
std::vector<playerent *> players;
playerent *player1=nullptr;
int lastmillis=100;
float corridor=100, ledge=100;
bool collide(botent *bot, bool, float, float) {
    if (fabs(bot->o.x)+bot->radius > corridor) return true;
    auto obstacles=players;
    if (player1) obstacles.push_back(player1);
    for (auto other: obstacles) {
        if (other==bot || !other->cancollide || other->state!=CS_ALIVE) continue;
        vec delta(other->o); delta.sub(bot->o);
        if (fabs(delta.x)<other->radius+bot->radius &&
            fabs(delta.y)<other->radius+bot->radius &&
            delta.dot(bot->vel)>=0) return true;
    }
    bot->onfloor=bot->o.x < ledge;
    // Exercise restoration of fields that the real collide() can alter.
    bot->vel.z=0;
    bot->o.z+=0.001f;
    return false;
}
struct CBot {
    botent *m_pMyEnt;
    int m_iBotAvoidTime=0, m_iBotBlockedTime=0;
    vec m_vBotAvoidDir, m_vBotBlockedOrigin;
    void AvoidPlayers();
    void ResetMoveSpeed() { m_pMyEnt->move=m_pMyEnt->strafe=0; }
};
'''
        scenarios = r'''
int main() {
    botent a, b;
    a.clientnum=1; b.clientnum=2;
    b.o.y=-3; b.yaw=180;
    players={&a, &b};
    CBot ai; ai.m_pMyEnt=&a;
    assert(BotPlayerInPath(&a, &b, BotMoveVector(0,1,0),2));
    assert(!BotPlayerInPath(&a, &b, BotMoveVector(0,-1,0),2));
    b.state=CS_DEAD;
    assert(!BotPlayerInPath(&a, &b, BotMoveVector(0,1,0),2));
    b.state=CS_ALIVE; b.o.z=20;
    assert(!BotPlayerInPath(&a, &b, BotMoveVector(0,1,0),2));
    b.o.z=0;

    // Open space: sidestep and preserve the world direction while aiming.
    a.vel=vec(1,2,3);
    ai.AvoidPlayers();
    assert(a.strafe==-1 && a.move==0 && !a.jumpnext);
    assert(a.o.dist(vec())==0 && a.vel.dist(vec(1,2,3))==0 && a.onfloor);
    vec escape=BotMoveVector(a.yaw,a.move,a.strafe);
    a.yaw=90; lastmillis+=50;
    ai.AvoidPlayers();
    assert(escape.dot(BotMoveVector(a.yaw,a.move,a.strafe))>0.99f);

    // Single-width corridor: the priority bot waits; the other backs away.
    corridor=1.4f; a.yaw=0; a.move=1; a.strafe=0;
    ai.m_iBotAvoidTime=ai.m_iBotBlockedTime=0;
    ai.AvoidPlayers();
    assert(a.move==0 && a.strafe==0);
    CBot bi; bi.m_pMyEnt=&b;
    bi.AvoidPlayers();
    assert(b.move==-1 && b.strafe==0);

    // A stationary queue eventually backs out instead of waiting forever.
    b.yaw=0; a.move=1;
    ai.m_iBotBlockedTime=lastmillis;
    lastmillis+=1600;
    ai.AvoidPlayers();
    assert(a.move==-1 && a.strafe==0);
    ai.m_iBotAvoidTime=0;
    b.yaw=180;

    // Once the player ahead clears, resume the requested movement.
    b.o.x=20; a.move=1;
    ai.AvoidPlayers();
    assert(a.move==1 && a.strafe==0 && ai.m_iBotBlockedTime==0);

    // Body-size clearance and ledge protection, with no probe side effects.
    corridor=1.4f;
    assert(!BotCanMove(&a,vec(1,0,0),1.5f));
    corridor=100; ledge=0.5f;
    assert(!BotCanMove(&a,vec(1,0,0),1.5f));
    assert(a.o.dist(vec())==0 && a.vel.dist(vec(1,2,3))==0 && a.onfloor);
    ledge=100;

    // Sweeping the footprint catches a player missed by a center-line ray.
    b.o=vec(2,-3,0);
    assert(BotPlayerInPath(&a,&b,vec(0,-1,0),2));

    // An overlapping player can be escaped by moving away.
    b.o=vec(0,-1,0);
    assert(BotCanMove(&a,vec(0,1,0),1.5f));

    // Human players receive priority, including the local player.
    players={&a}; player1=&b; b.type=ENT_PLAYER; b.o=vec(0,-3,0);
    corridor=1.4f; a.move=1; a.strafe=0;
    ai.m_iBotAvoidTime=ai.m_iBotBlockedTime=0;
    ai.AvoidPlayers();
    assert(a.move==-1 && a.strafe==0);
}
'''
        with tempfile.TemporaryDirectory(prefix="ac-bot-test-") as directory:
            path = Path(directory)
            (path / "avoidance.cpp").write_text(fixture + avoidance + scenarios)
            subprocess.run(["clang++", "-std=c++11", "-Wall", "-Wextra",
                            str(path / "avoidance.cpp"), "-o", str(path / "avoidance")], check=True)
            subprocess.run([str(path / "avoidance")], check=True)


if __name__ == "__main__":
    unittest.main()
