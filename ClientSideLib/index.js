/* Picture Streamer
 *
 * This file is part of the Picture Streamer project.
 * The program streams image previews from your DSLR or simular
 * camera to a web interface, allowing you to download pictures
 * the moment they've been taken.
 *
 * Copyright (C) 2015 Christian Beuschel <chris109@web.de>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; version 2 of the License.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
 */

function Page()
{
    // Pages in menu navigation
    this.photoFolder        = 'photo';
    this.thumnailFolder     = 'thumb';
    this.dataURI            = 'data.json';
    this.imageList          = [];
    this.imageCounter       = 0;
    this.isCameraConnected  = false;
    this.isNetworkConnected = false;
    this.isOptionMenuOpen   = false;

    this.opntionUseDirectAppLinks = false;

    this.init = function()
    {
        var context = this;
        $('#OptionMenuButton').click(function()
        {
            context.handleMenuClicked(this);
        });
    }

    this.handleMenuClicked = function(menuButton)
    {
        if (this.isOptionMenuOpen == false)
        {
            var context = this;
            menuDiv = $('<div>',
            {
                'id'   : 'OptionMenu',
                'class': 'Menu'
            });

            txt = (this.opntionUseDirectAppLinks == false) ? 'Use direct app liks' : 'Use normal links';
            menuEntryUseDirectAppLinks = $('<div>',
            {
                'class': 'MenuEntry',
                'text' : txt
            }).click(function()
            {
                context.handleMenuEntryUseDirectAppLinksClicked(this);
            });

            txt = 'Shutdown server'
            menuEntryShutdown = $('<div>',
            {
                'class': 'MenuEntry',
                'text' : txt
            }).click(function()
            {
                context.handleMenuEntryShutdownClicked(this);
            });

            $(menuDiv).append(menuEntryUseDirectAppLinks);
            $(menuDiv).append(menuEntryShutdown);
            $('body').append(menuDiv);
            this.isOptionMenuOpen = true;
        }
        else
        {
            $('#OptionMenu').remove();
            this.isOptionMenuOpen = false;
        }
    }

    this.handleMenuEntryUseDirectAppLinksClicked = function(menuEntry)
    {
        this.opntionUseDirectAppLinks = !this.opntionUseDirectAppLinks;
        txt = (this.opntionUseDirectAppLinks == false) ? 'Use direct app liks' : 'Use normal links';
        $(menuEntry).html(txt);
        if (this.opntionUseDirectAppLinks == true)
        {
            setTimeout(function()
            {
                $('a.Thumbnail').each(function()
                {
                    href = $(this).attr('href');
                    href = href.replace('http://', 'http-img-jpeg://');
                    $(this).attr('href', href);
                });
            }, 2);
        }
        else
        {
            setTimeout(function()
            {
                $('a.Thumbnail').each(function()
                {
                    href = $(this).attr('href');
                    href = href.replace('http-img-jpeg://', 'http://');
                    $(this).attr('href', href);
                });
            }, 2);
        }
        var context = this;
        setTimeout(function()
        {
            $('#OptionMenu').remove();
            context.isOptionMenuOpen = false;
        }, 1);
    }

    this.handleMenuEntryShutdownClicked = function(menuEntry)
    {
        var context = this;

        overlayDiv = $('<div>',
        {
            'id'   : 'GlobalOverlay',
            'class': 'Overlay'
        });
        formDiv = $('<div>',
        {
            'id'   : 'ShutdownFormFrame',
            'class': 'OverlayForm'
        });
        titleDiv = $('<div>',
        {
            'id'   : 'OverlayFormTitle',
            'class': 'OverlayFormTitle',
            'text' : 'Shutdown server'
        });
        form = $('<form>',
        {
            'id'   : 'ShutdownForm',
            'class': 'OverlayForm'
        }).submit(function()
        {
            return false;
        });
        rebootButton = $('<button>',
        {
            'id'   : 'RebootButton',
            'class': 'OverlayForm',
            'text' : 'Reboot'
        }).click(function()
        {
            context.sendForm(this);
        });
        shutdownButton = $('<button>',
        {
            'id'   : 'ShutdownButton',
            'class': 'OverlayForm',
            'text' : 'Shutdown'
        }).click(function()
        {
            context.sendForm(this);
        });
        cancelButton = $('<button>',
        {
            'id'   : 'ShutdownCancelButton',
            'class': 'OverlayForm',
            'text' : 'Cancel'
        }).click(function()
        {
            context.removeOverlay(this);
        });

        $('body').append(overlayDiv);
        $(overlayDiv).append(formDiv);
        $(formDiv).append(titleDiv);
        $(formDiv).append(form);
        $(form).append(rebootButton);
        $(form).append(shutdownButton);
        $(formDiv).append(cancelButton);

        setTimeout(function()
        {
            $('#OptionMenu').remove();
            context.isOptionMenuOpen = false;
        }, 1);
    }

    this.removeOverlay = function(senderElement)
    {
        $('#GlobalOverlay').remove();
    }

    this.sendForm = function(senderElement)
    {
        if ($(senderElement).attr('id') == 'RebootButton')
        {
            command = 'reboot';

        }
        else if  ($(senderElement).attr('id') == 'ShutdownButton')
        {
            command = 'shutdown';
        }
        else
        {
            command = '';
        }

        $.ajax({
            method: 'POST',
            url: ('shutdown.api'),
            context: this,
            data:
            {
                'command': command,
            },
            success:function(data, status, request)
            {
                $('form#ShutdownForm').remove();
                if (data == 'REBOOT')
                {
                    messageDiv = $('<div>',
                    {
                        'class': 'OverlayMessageDiv',
                        'text' : 'Reboot running ...'
                    });
                    $('#ShutdownCancelButton').remove();
                    context = this;
                    setTimeout(function(){context.removeOverlay();}, 30000);
                }
                else if (data == 'SHUTDOWN')
                {
                    messageDiv = $('<div>',
                    {
                        'class': 'OverlayMessageDiv',
                        'text' : 'Shutdown running ...'
                    });
                    $('#ShutdownCancelButton').remove();
                    context = this;
                    setTimeout(function(){context.removeOverlay();}, 55000);
                }
                else if (data == 'ACCESS_DENIED')
                {
                    messageDiv = $('<div>',
                    {
                        'class': 'OverlayFormError',
                        'text' : 'Access denied!'
                    });
                }
                else if (data == 'OPERATION_NOT_AVAILABLE')
                {
                    messageDiv = $('<div>',
                    {
                        'class': 'OverlayFormError',
                        'text' : 'This feature is not available!'
                    });
                }
                else
                {
                    messageDiv = $('<div>',
                    {
                        'class': 'OverlayFormError',
                        'text' : 'Unknown error!'
                    });
                }
                $('div#OverlayFormTitle').after(messageDiv);
            },
            error:function(request, result, error)
            {
                $('form#ShutdownForm').remove();
                errorDiv = $('<div>',
                {
                    'class': 'OverlayFormError',
                    'text' : 'Netzwerkfehler! Versuchen sie es später erneut.'
                });
                $('div#OverlayFormTitle').after(errorDiv);
            }
        });

        return false;
    }

    this.openURL = function(webLink, customLink)
    {
        var fallbackLink = webLink;

        // Simple device detection
        var isiOS     = navigator.userAgent.match('iPad') ||
                        navigator.userAgent.match('iPhone') ||
                        navigator.userAgent.match('iPod');

        var isAndroid = navigator.userAgent.match('Android');

        // Mobile
        if (isiOS || isAndroid)
        {
          // Load our custom protocol in the iframe, for Chrome and Opera this burys the error dialog (which is actually HTML)
          // for iOS we will get a popup error if this protocol is not supported, but it won't block javascript
          document.getElementById('loader').src = customLink;
        }

        // Now we just wait for everything to execute, if the user is redirected to your custom app
        // the timeout below will never fire, if a custom app is not present (or the user is on the Desktop)
        // we will replace the current URL with the fallbackLink (store URL or desktop URL as appropriate)
        window.setTimeout(function()
        {
            window.location.replace(fallbackLink);
        }, 1);
    }

    this.handleLinkClicked = function(a)
    {
        txt = $('<div class="ThumbnailOverlay ThumbnailOverlayHidden">DOWNLOADED</div>');
        $(a).append(txt);
        return true;
    }

    this.loadContent = function()
    {
        $.ajax({
            url: ('data.json?count=' + this.imageCounter),
            context: this,
            success:function(data, status, request)
            {
                // Update network state
                if (this.isNetworkConnected == false)
                {
                    $('#StateValue_NetworkState_Connected').removeClass('HiddenValue');
                    $('#StateValue_NetworkState_Disconnected').addClass('HiddenValue');
                }
                this.isNetworkConnected = true;

                // Upadate camera state
                if (this.isCameraConnected != (data['isCameraConnected'] == 1))
                {
                    this.isCameraConnected = (data['isCameraConnected'] == 1);
                    if (this.isCameraConnected == true)
                    {
                        $('#StateValue_CameraState_Connected').removeClass('HiddenValue');
                        $('#StateValue_CameraState_Disconnected').addClass('HiddenValue');
                    }
                    else
                    {
                        $('#StateValue_CameraState_Connected').addClass('HiddenValue');
                        $('#StateValue_CameraState_Disconnected').removeClass('HiddenValue');
                    }
                }
                if (data['imageCounter'] > this.imageCounter)
                {
                    // Update images
                    context = this
                    this.imageCounter = data['imageCounter'];
                    reversedList = data['imageList'];
                    reversedList.reverse();
                    for (imageIndex in reversedList)
                    {
                        imageName = data['imageList'][imageIndex]
                        this.imageList.push(imageName);
                        frameDiv = $('<div>', { 'class': 'ThumbnailFrame' });
                        thumbDiv = $('<div>', { 'class': 'Thumbnail' });
                        a = $('<a>',
                        {
                            'class': 'Thumbnail Minimized',
                            'href': window.location.protocol + '//' + window.location.hostname + ':' + window.location.port + '/' + this.photoFolder + '/' + imageName
                        });
                        a.click(function(){ return context.handleLinkClicked(this); });
                        img = $('<img>', { class: 'Thumbnail', src: this.thumnailFolder + '/' + imageName, alt: imageName });
                        txt = $('<div class="ThumbnailText">' + imageName + '</div>');
                        $(a).append(img);
                        $(a).append(txt);
                        $(thumbDiv).append(a);
                        $(frameDiv).append(thumbDiv);
                        $('#ThumbnailList').prepend(frameDiv);
                    }
                    setTimeout(function(){$('a.Minimized').removeClass('Minimized');}, 10);
                }
                // Start next update interval with 100ms
                var context = this;
                setTimeout(function(){context.loadContent();}, 100);
            },
            error:function(request, result, error)
            {
                // Update network state
                if (this.isNetworkConnected == true)
                {
                    $('#StateValue_NetworkState_Connected').addClass('HiddenValue');
                    $('#StateValue_NetworkState_Disconnected').removeClass('HiddenValue');
                }
                this.isNetworkConnected = false;
                // Start next update interval with 5s
                var context = this;
                setTimeout(function(){context.loadContent();}, 5000);
            }
        });
    }
}


$(document).ready(function()
{
    page = new Page();
    page.init();
    page.loadContent();
});
