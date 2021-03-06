__author__ = "Marko Maric"
__copyright__ = "Copyright 2018, Croatian Academic and Research Network (CARNET)"

from pyvirtualdisplay import Display

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.alert import Alert

from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException, StaleElementReferenceException
import time as time_

from bs4 import BeautifulSoup


import sys  #for exit()
import codecs

import re
import spamsum

import psycopg2

from datetime import datetime

import traceback
import time

import urllib2

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)  #treba za printanje Unicoda u file

conn = psycopg2.connect("dbname='webdfcdb4' user='webdfc' host='localhost' password='webdfc'")


display = Display(visible=0, size=(800, 600))
display.start()

browser = webdriver.Chrome('/home/marko/workspace/chromedriver')

class Stale():
    pass

STALE = Stale()
ALERT_CONFIRMS = 10

def visible(element):
    if element.parent.name in ['style', 'script', '[document]', 'head']:
        return False
    elif re.match('<!--.*-->', element):
        return False
    elif element.strip() == '':
        return False
    else:
        return True


def processDefacement(time, notifier, url, mirrorsrc):

    elements = getElements(mirrorsrc)

    elements = filterValidElements(elements)

    elements = calculateFuzzy(elements)

    insertInDatabase(notifier, time, url, elements, mirrorsrc)


#Function enables recovery if element disappears from DOM tree or webpage is refreshed

def getDynamicElements(getFunction, *args):

    try:
        return getFunction(*args)
    except StaleElementReferenceException as e:
        print "Stale element"
        return STALE
          

#Discards None or anything shorter than three symbols

def filterValidElements(elements):

    for key in elements:

        elements[key] = filter(lambda x: False if x == None or x == STALE or len(x) < 3 else True, elements[key])

    return elements


    allElems = {'alerts': [], 'texts': [], 'images': [], 'backgroundImages': [], 'music': []}



def insertInDatabase(notifier, time, url, elements, mirrorsrc):

    #Insert in database
    print elements
    print "\n"
 
    dataType = lambda basictype, size: 'L' + basictype if size <= 1000 else 'H' + basictype

    curr = conn.cursor()

    notifier_id = None
    #adding new notifier in 'notifier' table if does not exists
    curr.execute("SELECT id FROM notifier WHERE name=%s", (notifier,))
    result = curr.fetchall()
    if len(result) == 0:
        curr.execute("INSERT INTO notifier (name) VALUES (%s) RETURNING id;", (notifier,))
        notifier_id = curr.fetchone()[0]
    else:
        notifier_id = result[0][0]

    #adding new deface in 'defaces' table
    #TODO: Adds wrong date if time after 21:00/22:00
    today = datetime.today()
    time = datetime.strptime('%s %s %s ' % (today.day, today.month, today.year) + time, '%d %m %Y %H:%M')
    curr.execute("INSERT INTO defaces (time, notifier_id, url, mirrorsrc) VALUES (%s, %s, %s, %s) RETURNING id;", (time, notifier_id, url, mirrorsrc))
    defaces_id = curr.fetchone()[0]
    #Adding new element if does not exists in 'elements_defaces'
    for key, values in elements.iteritems():
            for value in values:

                data = bytearray(value[0], 'utf-8') if isinstance(value[0], unicode) else bytearray(value[0])

                curr.execute("SELECT id FROM elements_defaces WHERE type=%s AND element=%s", \
                                                                (dataType(key, len(data)), data))
                result = curr.fetchall()
                if len(result) == 0:
                    curr.execute("INSERT INTO elements_defaces (type, element, hash, resource) VALUES (%s, %s, %s, %s) RETURNING id;", \
                                                                (dataType(key, len(data)), data, value[1], value[2]))
                    elements_dafaces_id = curr.fetchone()[0]
                else:
                    elements_dafaces_id = result[0][0]
    
                #for each pair 'defaces'-'elements_defaces' adding new entry in defaces_elements_defaces
                curr.execute("INSERT INTO defaces_elements_defaces (defaces_id, elements_defaces_id) VALUES (%s, %s) RETURNING id;",\
                                 (defaces_id, elements_dafaces_id))

    curr.close()
    conn.commit()
    

def calculateFuzzy(elements):
    print "**********************************************************************************************\n"
    print elements

    pics = {}
    for key, value in elements.iteritems():

        if key in ('images', 'backgroundImages'):

            for url in value:
                try:
                    if not url in pics:
                        pic = urllib2.urlopen(url).read()
                        pics[url] = pic
                except (urllib2.HTTPError, urllib2.URLError) as e:
                    print "Not able to download image: %s\n" % (url, )
                    pics[url] = None
                except ValueError as e:
                    if 'unknown url type' in str(e):
                        print "Incorrectly formatted URL.\n"
                        pics[url] = None
                    else:
                        raise e

            elements[key] = filter(lambda (x, y, z): not y == None, \
                            map(  lambda x: (None, None, x) if pics[x] == None else (pics[x], spamsum.spamsum(pics[x]), x) , value))

        elif key in ('alerts', 'texts'):

            elements[key] = map(  lambda x: (x, spamsum.spamsum(x.encode('utf-8')), None) , value)

        else:   #music

            elements[key] = map(lambda x: (x.split(u'?')[0], spamsum.spamsum(x.split(u'?')[0]), x), value) 

    return elements


def getElementContent(allElems):

    #downloading images and backgroundImages
    return allElems


def getElements(mirrorsrc):

    #creating dictionary of Elements
    allElems = {'alerts': [], 'texts': [], 'images': [], 'backgroundImages': [], 'music': []}

    browser.get(mirrorsrc)

    try:

        for i in range(0, ALERT_CONFIRMS + 1):       #number of alert confirms: 10 alerts and content

            try:

                try:
                    WebDriverWait(browser, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, "body"))
                                )
                except TimeoutException as e:
                    print "Time elapsed for zone-h page processing getElements\n"
                    break
                else:
                    time_.sleep(2)  #safety hold in case HTML is not fully loaded, and time for potential another alert

                    soup = BeautifulSoup(browser.page_source, 'html.parser')
                    
                    #Downloading all element types
                    #All visible text
                    texts = soup.findAll(text=True)
                    visible_texts = filter(visible, texts)  
                    allElems['texts'] = visible_texts

                    #Images (img tagovi)
                    images = browser.find_elements_by_tag_name('img')
                    images = map(lambda x: getDynamicElements(x.get_attribute, 'src'), images)
                    fimageurls = images

                    allElems['images'] = fimageurls
                    
                    #Background images

                    allNodes = browser.find_elements_by_xpath("//*")

                    allBackImageURLs = map(lambda x: getDynamicElements(x.value_of_css_property, 'background-image'), allNodes)

                    #Although None and STALE are filtered afterwards in filterValidElements
                    allBackImageURLsFiltered = filter(lambda x: False if x in [u'none', u'', None, STALE] else True, allBackImageURLs)

                    allBackImageURLsFiltered = map(lambda x: x[5:-2], allBackImageURLsFiltered)

                    allElems['backgroundImages'] = allBackImageURLsFiltered         #Check for background value is needed as well!!
                    
                    #Music (embed:src, iframe:src,  - width=height=0 does not have to be!!)

                    musicLinks1 = map(lambda x: getDynamicElements(x.get_attribute, 'src'), browser.find_elements_by_tag_name('embed'))
                    musicLinks2 = map(lambda x: getDynamicElements(x.get_attribute, 'src'), browser.find_elements_by_tag_name('iframe'))

                    musicLinks = musicLinks1 + musicLinks2

                    allElems['music'] = musicLinks
                    break


            except UnexpectedAlertPresentException as e:
                print "Accepting alert in getElements: %s\n" % (Alert(browser).text,)

                allElems['alerts'].append(Alert(browser).text)
                allElems['texts'] = []
                allElems['images'] = []
                allElems['backgroundImages'] = []
                allElems['music'] = []

                if i == ALERT_CONFIRMS:
                    print traceback.format_exc()
                    print "\n"

                #Accept alert
                Alert(browser).accept()

    except:
        print "Unsuccessful processing of getElements\n"
        print traceback.format_exc()
        print "\n"


    allElemsWithContent = getElementContent(allElems)

    return allElemsWithContent



def process_zoneh_pages(f):

    ttime, tnotifier, tmirror = ctime, cnotifier, cmirror = f.read().split('\n')[:3]
    tnotifier = cnotifier = cnotifier.decode('utf-8')
    allData = []
     
    print [ctime, cnotifier, cmirror] 
    print "\n"

    i = -1

    for pagenum in range(1, 3):     #looking for defaces in first two pages

        try:
            print pagenum

            #TODO: Connecting over TOR (captcha recognition and change of circuit)
            browser.get('http://zone-h.org/archive/page=%d' % (pagenum,))

            try:
                WebDriverWait(browser, 10).until(
                            EC.presence_of_element_located((By.ID, "ldeface"))
                            )

            except TimeoutException as e:
                print "Time elapsed for zone-h page processing\n"

            else:
                mirrors = browser.find_elements_by_link_text('mirror')
                ntdata = map(lambda x: x.find_elements_by_xpath("../../*"), mirrors)
                data = map(lambda (x, y): (x[0].text, x[1].text, y.get_attribute('href')), zip(ntdata, mirrors))

                allData += data

                if (ctime, cnotifier, cmirror) in data:
                    i = data.index((ctime, cnotifier, cmirror))
                    allData = list(reversed(allData[:i]))
                    break

        except:
            print "Unsuccessful processing of zone-h page\n"
            print traceback.format_exc()
            print "\n"
            
    if i == -1:
        allData = list(reversed(allData))

    return allData


def process_deface_pages(allData):

        for time, notifier, mirror in allData:

            try:

                print notifier, time, mirror

                browser.get(mirror)

                for i in range(0, ALERT_CONFIRMS + 1):       #broj potvrda alerta: 10 alerta i content

                    try:

                        try:
                            WebDriverWait(browser, 10).until(
                                        EC.presence_of_element_located((By.TAG_NAME, "iframe"))
                                        )
                        except TimeoutException as e:
                            print "Time elapsed for zone-h page processing\n"
                            break
                        else:
                            time_.sleep(2)  #sigurnosno cekanje ukoliko html nije ucitan do kraja

                            mirrorsrc = browser.find_element_by_tag_name('iframe').get_attribute('src')
                            url = browser.find_elements_by_xpath("//*[@id='propdeface']/ul/li[2]/ul[1]/li[2]")[0].text.split(": ")[1].strip()

                            print url
                            print "\n"

                            processDefacement(time, notifier, url, mirrorsrc)
                            break


                    except UnexpectedAlertPresentException as e:
                        print "Accepting alert in process_deface_pages\n"
                        #potvrda alerta ovdje
                        Alert(browser).accept()
                        if i == ALERT_CONFIRMS:
                            print traceback.format_exc()
                            print "\n"

            except:
                print "Unsuccessful processing of zone-h page\n"
                print traceback.format_exc()
                print "\n"                    




def main():


    try:
        f = open("deface.temp", "r+")

        allData = process_zoneh_pages(f)
        process_deface_pages(allData)

        if not allData == []:
            ttime, tnotifier, tmirror = allData[-1] #index not in range error znaci da se nije pojavio novi deface page od zadnjeg pokretanja
            f.seek(0)
            f.write(ttime + "\n")
            f.write(tnotifier.encode('utf-8') + "\n")
            f.write(tmirror)
            f.truncate()
        else:
            print "There is no new web defacemens!\n"

        print "Successfully done.\n"
    except:
        print "Unsuccessfully done.\n"
        print traceback.format_exc()
        print "\n"
    finally:
        f.close()
        browser.quit()
        conn.close()
 


print "----------------------------------------------------%s\
---------------------------------------------------------------------------------\n"  % (time.strftime("%c"),)
main()


